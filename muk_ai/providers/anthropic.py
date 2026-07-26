from __future__ import annotations

import json
from collections.abc import Callable

from odoo.addons.muk_ai.providers.base import ProviderBase

ANTHROPIC_VERSION = '2023-06-01'
WEB_SEARCH_TOOL_TYPE = 'web_search_20250305'
CODE_EXECUTION_TOOL_TYPE = 'code_execution_20250825'

THINKING_MODEL_TOKENS = ('fable-5', 'opus-4', 'sonnet-5', 'sonnet-4', '3-7-sonnet')
LEGACY_THINKING_MODEL_TOKENS = (
    'opus-4-0',
    'opus-4-1',
    'opus-4-5',
    'opus-4-6',
    '3-7-sonnet',
    'sonnet-4-0',
    'sonnet-4-5',
    'sonnet-4-6',
)
LEGACY_THINKING_BUDGETS = {
    'medium': 1024,
    'high': 4096,
    'xhigh': 8192,
    'max': 16384,
}

CACHE_CONTROL = {'type': 'ephemeral'}


class AnthropicProvider(ProviderBase):
    """Anthropic Messages API adapter with thinking and streaming support."""

    name = 'anthropic'
    label = 'Anthropic'
    default_model = 'claude-sonnet-4-6'
    default_url = 'https://api.anthropic.com/v1'

    supports_web_search = True
    supports_image_generation = False
    supports_code_interpreter = True

    reasoning_error_tokens = ('thinking', 'effort', 'output_config')

    # ----------------------------------------------------------
    # Contract
    # ----------------------------------------------------------

    def headers(self) -> dict:
        """Return the Anthropic request headers including the API version."""
        return {
            'x-api-key': self.api_key,
            'anthropic-version': ANTHROPIC_VERSION,
            'Content-Type': 'application/json',
        }

    def request(
        self,
        inputs,
        tools_schema=None,
        text_schema=None,
        on_delta=None,
        model=None,
        enable_web_search=False,
        enable_image_generation=False,
        enable_code_interpreter=False,
        extra=None,
    ) -> dict:
        """Build and run a Messages request, retrying once without thinking on error."""
        model = self.model_for(model)
        caching = self._supports_caching(model)
        system_text, messages, anchor = self._inputs_to_messages(inputs)
        max_tokens = self.max_tokens or 4096
        body = {
            'model': model,
            'messages': messages,
            'max_tokens': max_tokens,
        }
        effort = (extra or {}).get('reasoning_effort')
        adaptive = self._uses_adaptive_thinking(model)
        if self._supports_thinking(model):
            if adaptive:
                body['thinking'] = {'type': 'adaptive'}
                if effort:
                    body['output_config'] = {
                        'effort': 'low' if effort == 'minimal' else effort,
                    }
            elif budget := LEGACY_THINKING_BUDGETS.get(effort):
                if max_tokens <= budget:
                    body['max_tokens'] = budget + 1024
                body['thinking'] = {
                    'type': 'enabled',
                    'budget_tokens': budget,
                }
        if system_text:
            body['system'] = (
                [{'type': 'text', 'text': system_text, 'cache_control': CACHE_CONTROL}]
                if caching
                else system_text
            )
        tools = self._tools_to_anthropic(tools_schema)
        if enable_web_search:
            tools.append(
                {
                    'type': WEB_SEARCH_TOOL_TYPE,
                    'name': 'web_search',
                }
            )
        if enable_code_interpreter:
            tools.append(
                {
                    'type': CODE_EXECUTION_TOOL_TYPE,
                    'name': 'code_execution',
                }
            )
        if tools:
            if caching:
                tools[-1] = {**tools[-1], 'cache_control': CACHE_CONTROL}
            body['tools'] = tools
        if caching and anchor is not None:
            msg_index, block_index = anchor
            messages[msg_index]['content'][block_index]['cache_control'] = CACHE_CONTROL
        return self._invoke_with_reasoning_retry(
            model,
            lambda callback: self._invoke(body, callback),
            on_delta,
            ((body, ('output_config',) if adaptive else ('thinking',)),),
        )

    # ----------------------------------------------------------
    # Thinking
    # ----------------------------------------------------------

    def _invoke(self, body: dict, on_delta: Callable | None) -> dict:
        """Dispatch the request to the streaming or non-streaming path."""
        if callable(on_delta):
            return self._stream(body, on_delta)
        return self._parse_response(self._post_json('/messages', body))

    @staticmethod
    def _supports_thinking(model: str) -> bool:
        """Return whether the model supports extended thinking."""
        return any(token in model for token in THINKING_MODEL_TOKENS)

    @staticmethod
    def _supports_caching(model: str) -> bool:
        """Return whether the model supports prompt caching via cache_control."""
        return model.startswith('claude')

    @staticmethod
    def _uses_adaptive_thinking(model: str) -> bool:
        """Return whether the model uses adaptive (vs budgeted) thinking."""
        return not any(token in model for token in LEGACY_THINKING_MODEL_TOKENS)

    # ----------------------------------------------------------
    # Inputs
    # ----------------------------------------------------------

    @staticmethod
    def _text_from_content(content) -> str:
        """Flatten a content value (string or block list) into plain text."""
        if isinstance(content, str):
            return content
        parts = []
        for chunk in content or []:
            text = chunk.get('text')
            if text:
                parts.append(text)
        return ''.join(parts)

    @classmethod
    def _inputs_to_messages(
        cls, inputs
    ) -> tuple[str, list[dict], tuple[int, int] | None]:
        """Convert canonical inputs into Anthropic system text, messages, and anchor.

        The anchor is the ``(message, block)`` index of the last content block
        built from a non-volatile input — the safe spot for a conversation
        cache breakpoint, sitting before per-round trailers that would
        otherwise re-write the cache every round.
        """
        system_parts = []
        messages = []
        anchor = None

        def append(role, block):
            if messages and messages[-1]['role'] == role:
                messages[-1]['content'].append(block)
            else:
                messages.append({'role': role, 'content': [block]})
            return len(messages) - 1, len(messages[-1]['content']) - 1

        for item in inputs or []:
            item_type = item.get('type')
            role = item.get('role')
            volatile = bool(item.get('_cache_volatile'))
            if role == 'system':
                text = cls._text_from_content(item.get('content'))
                if text:
                    system_parts.append(text)
                continue
            if item_type == 'function_call':
                try:
                    arguments = json.loads(item.get('arguments') or '{}')
                except ValueError:
                    arguments = {}
                position = append(
                    'assistant',
                    {
                        'type': 'tool_use',
                        'id': item.get('call_id'),
                        'name': item.get('name'),
                        'input': arguments,
                    },
                )
                if not volatile:
                    anchor = position
                continue
            if item_type == 'function_call_output':
                output = item.get('output')
                if not isinstance(output, str):
                    output = json.dumps(output, default=str)
                position = append(
                    'user',
                    {
                        'type': 'tool_result',
                        'tool_use_id': item.get('call_id'),
                        'content': output,
                    },
                )
                if not volatile:
                    anchor = position
                continue
            if role in ('user', 'assistant'):
                for block in cls._content_to_anthropic(item.get('content')):
                    position = append(role, block)
                    if not volatile:
                        anchor = position

        return '\n\n'.join(system_parts), messages, anchor

    @classmethod
    def _content_to_anthropic(cls, content) -> list[dict]:
        """Convert canonical content blocks into Anthropic content blocks."""
        if isinstance(content, str):
            return [{'type': 'text', 'text': content}]
        blocks = []
        for chunk in content or []:
            if not isinstance(chunk, dict):
                continue
            chunk_type = chunk.get('type')
            if chunk_type == 'muk_ai_attachment':
                blocks.append(cls._attachment_to_anthropic(chunk))
            elif chunk_type == 'muk_ai_thinking':
                if chunk.get('thinking'):
                    blocks.append(
                        {
                            'type': 'thinking',
                            'thinking': chunk['thinking'],
                            'signature': chunk.get('signature') or '',
                        }
                    )
            elif chunk.get('text'):
                blocks.append({'type': 'text', 'text': chunk['text']})
        return blocks

    @staticmethod
    def _attachment_to_anthropic(block: dict) -> dict:
        """Convert an attachment block into an Anthropic image/document/text block."""
        strategy = block.get('strategy')
        mimetype = block.get('mimetype') or 'application/octet-stream'
        data_b64 = block.get('data_b64') or ''
        filename = block.get('filename') or 'attachment'
        if strategy == 'image':
            return {
                'type': 'image',
                'source': {
                    'type': 'base64',
                    'media_type': mimetype,
                    'data': data_b64,
                },
            }
        if strategy == 'file' and mimetype == 'application/pdf':
            return {
                'type': 'document',
                'source': {
                    'type': 'base64',
                    'media_type': 'application/pdf',
                    'data': data_b64,
                },
            }
        text = block.get('inline_text') or ''
        prefix = f'--- File: {filename} ({mimetype}) ---\n'
        if block.get('truncated'):
            text += '\n[truncated]'
        return {'type': 'text', 'text': prefix + text}

    @staticmethod
    def _tools_to_anthropic(tools_schema) -> list[dict]:
        """Convert tool schemas to Anthropic tool definitions, deduplicated by name."""
        if not tools_schema:
            return []
        seen = set()
        out = []
        for tool in tools_schema:
            name = tool['name']
            if name in seen:
                continue
            seen.add(name)
            out.append(
                {
                    'name': name,
                    'description': tool.get('description') or '',
                    'input_schema': tool.get('parameters')
                    or {
                        'type': 'object',
                        'properties': {},
                    },
                }
            )
        return out

    # ----------------------------------------------------------
    # Parse
    # ----------------------------------------------------------

    def _parse_response(self, payload: dict) -> dict:
        """Parse a non-streaming response into text, tool calls, carry inputs, and usage."""
        content = payload.get('content') or []
        text_parts = []
        tool_calls = []
        function_call_carries = []
        assistant_content = []
        for block in content:
            block_type = block.get('type')
            if block_type == 'text':
                text = block.get('text') or ''
                if text:
                    text_parts.append(text)
                    assistant_content.append(
                        {
                            'type': 'output_text',
                            'text': text,
                        }
                    )
            elif block_type == 'thinking':
                thinking = block.get('thinking') or ''
                if thinking:
                    assistant_content.append(
                        {
                            'type': 'muk_ai_thinking',
                            'thinking': thinking,
                            'signature': block.get('signature') or '',
                        }
                    )
            elif block_type == 'tool_use':
                call_id = block.get('id')
                name = block.get('name')
                arguments = block.get('input') or {}
                tool_calls.append(
                    {
                        'call_id': call_id,
                        'name': name,
                        'arguments': arguments,
                        '_parse_error': None,
                    }
                )
                function_call_carries.append(
                    {
                        'type': 'function_call',
                        'name': name,
                        'arguments': json.dumps(arguments, default=str),
                        'call_id': call_id,
                    }
                )
        carry_inputs = []
        if assistant_content:
            carry_inputs.append(
                {
                    'role': 'assistant',
                    'content': assistant_content,
                }
            )
        carry_inputs.extend(function_call_carries)
        result = {
            'text': '\n'.join(text_parts).strip(),
            'tool_calls': tool_calls,
            'carry_inputs': carry_inputs,
            'usage': self._usage_from_anthropic(payload.get('usage') or {}),
        }
        if payload.get('stop_reason') == 'max_tokens':
            self._apply_truncation(result, limit=self.max_tokens or 4096)
        return result

    @classmethod
    def _usage_from_anthropic(cls, usage: dict) -> dict:
        """Normalize Anthropic usage, folding cache tokens back into the total.

        Anthropic's ``input_tokens`` counts only the freshly-read (uncached)
        prompt, so cache reads and writes must be added back to recover the
        full prompt size the cost model and auto-compaction rely on.
        """
        uncached = usage.get('input_tokens') or 0
        cache_read = usage.get('cache_read_input_tokens') or 0
        cache_write = usage.get('cache_creation_input_tokens') or 0
        return cls._usage(
            input_tokens=uncached + cache_read + cache_write,
            output_tokens=usage.get('output_tokens'),
            cache_read_tokens=cache_read,
            cache_write_tokens=cache_write,
        )

    # ----------------------------------------------------------
    # Streaming
    # ----------------------------------------------------------

    def _stream(self, body: dict, on_delta) -> dict:
        """Stream a Messages request, emitting deltas and assembling the final result."""
        body = {**body, 'stream': True}
        blocks_by_index = {}
        raw_usage = {}
        meta = {}
        for event in self._post_stream('/messages', body):
            self._handle_stream_event(event, on_delta, blocks_by_index, raw_usage, meta)

        text_parts = []
        tool_calls = []
        function_call_carries = []
        assistant_content = []
        for index in sorted(blocks_by_index):
            entry = blocks_by_index[index]
            entry_type = entry.get('type')
            if entry_type == 'thinking':
                if entry.get('thinking'):
                    assistant_content.append(
                        {
                            'type': 'muk_ai_thinking',
                            'thinking': entry['thinking'],
                            'signature': entry.get('signature') or '',
                        }
                    )
            elif entry_type == 'text':
                text = entry.get('text') or ''
                if text:
                    text_parts.append(text)
                    assistant_content.append(
                        {
                            'type': 'output_text',
                            'text': text,
                        }
                    )
            elif entry_type == 'tool_use':
                args, parse_error = self._parse_tool_arguments(
                    entry.get('partial_json'),
                )
                tool_calls.append(
                    {
                        'call_id': entry['call_id'],
                        'name': entry['name'],
                        'arguments': args,
                        '_parse_error': parse_error,
                    }
                )
                function_call_carries.append(
                    {
                        'type': 'function_call',
                        'name': entry['name'],
                        'arguments': json.dumps(args, default=str),
                        'call_id': entry['call_id'],
                    }
                )
        carry_inputs = []
        if assistant_content:
            carry_inputs.append(
                {
                    'role': 'assistant',
                    'content': assistant_content,
                }
            )
        carry_inputs.extend(function_call_carries)
        result = {
            'text': ''.join(text_parts).strip(),
            'tool_calls': tool_calls,
            'carry_inputs': carry_inputs,
            'usage': self._usage_from_anthropic(raw_usage),
        }
        if meta.get('stop_reason') == 'max_tokens':
            self._apply_truncation(result, on_delta, self.max_tokens or 4096)
        return result

    def _handle_stream_event(
        self, event: dict, on_delta, blocks_by_index: dict, raw_usage: dict, meta: dict
    ) -> None:
        """Apply one streaming event to the accumulators and forward deltas.

        Token counts are collected as raw Anthropic fields in ``raw_usage``
        and normalized once by :meth:`_usage_from_anthropic` after the
        stream; the final ``stop_reason`` is collected in ``meta``.
        """
        event_type = event.get('type') or ''
        if event_type == 'message_start':
            start_usage = (event.get('message') or {}).get('usage') or {}
            raw_usage.update(
                {
                    'input_tokens': start_usage.get('input_tokens', 0),
                    'cache_read_input_tokens': start_usage.get(
                        'cache_read_input_tokens', 0
                    ),
                    'cache_creation_input_tokens': start_usage.get(
                        'cache_creation_input_tokens', 0
                    ),
                }
            )
        elif event_type == 'content_block_start':
            index = event.get('index', 0)
            block = event.get('content_block') or {}
            block_type = block.get('type')
            if block_type == 'text':
                blocks_by_index[index] = {'type': 'text', 'text': ''}
            elif block_type == 'thinking':
                blocks_by_index[index] = {
                    'type': 'thinking',
                    'thinking': block.get('thinking') or '',
                    'signature': block.get('signature') or '',
                }
            elif block_type == 'tool_use':
                entry = {
                    'type': 'tool_use',
                    'call_id': block.get('id'),
                    'name': block.get('name'),
                    'partial_json': '',
                }
                blocks_by_index[index] = entry
                self._call_on_delta(
                    on_delta,
                    'tool_start',
                    {
                        'call_id': entry['call_id'],
                        'name': entry['name'],
                    },
                )
        elif event_type == 'content_block_delta':
            index = event.get('index', 0)
            entry = blocks_by_index.get(index)
            if entry is None:
                return
            delta = event.get('delta') or {}
            delta_type = delta.get('type')
            if delta_type == 'text_delta' and entry.get('type') == 'text':
                text = delta.get('text') or ''
                if not text:
                    return
                entry['text'] += text
                self._call_on_delta(on_delta, 'text', {'delta': text})
            elif delta_type == 'thinking_delta' and entry.get('type') == 'thinking':
                text = delta.get('thinking') or ''
                if not text:
                    return
                entry['thinking'] += text
                self._call_on_delta(on_delta, 'reasoning', {'delta': text})
            elif delta_type == 'signature_delta' and entry.get('type') == 'thinking':
                signature = delta.get('signature') or ''
                if signature:
                    entry['signature'] = (entry.get('signature') or '') + signature
            elif delta_type == 'input_json_delta' and entry.get('type') == 'tool_use':
                partial = delta.get('partial_json') or ''
                if not partial:
                    return
                entry['partial_json'] += partial
                self._call_on_delta(
                    on_delta,
                    'tool_args',
                    {
                        'call_id': entry['call_id'],
                        'delta': partial,
                    },
                )
        elif event_type == 'message_delta':
            if stop_reason := (event.get('delta') or {}).get('stop_reason'):
                meta['stop_reason'] = stop_reason
            delta_usage = event.get('usage') or {}
            if 'output_tokens' in delta_usage:
                raw_usage['output_tokens'] = delta_usage['output_tokens']
        elif event_type == 'error':
            error = event.get('error') or {}
            self._raise(error.get('message') or 'Unknown streaming error')
