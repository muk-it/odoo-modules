from __future__ import annotations

import json
from collections.abc import Callable

from odoo.addons.muk_ai.providers.base import ProviderBase

ANTHROPIC_VERSION = '2023-06-01'
WEB_SEARCH_TOOL_TYPE = 'web_search_20250305'
CODE_EXECUTION_TOOL_TYPE = 'code_execution_20250825'

THINKING_MODEL_TOKENS = ('fable-5', 'opus-5', 'opus-4', 'sonnet-5', 'sonnet-4')
LEGACY_THINKING_MODEL_TOKENS = (
    'opus-4-5',
    'sonnet-4-5',
)
LEGACY_THINKING_BUDGETS = {
    'medium': 1024,
    'high': 4096,
    'xhigh': 8192,
    'max': 16384,
}

STRUCTURED_OUTPUT_MODEL_TOKENS = (
    'fable-5',
    'opus-5',
    'opus-4-8',
    'opus-4-5',
    'opus-4-1',
    'sonnet-5',
    'haiku-4-5',
)

THINKING_BLOCK_TYPES = ('thinking', 'redacted_thinking')

CACHE_CONTROL = {'type': 'ephemeral'}


class AnthropicProvider(ProviderBase):
    """Anthropic Messages API adapter with thinking and streaming support."""

    name = 'anthropic'
    label = 'Anthropic'
    default_model = 'claude-sonnet-5'
    default_url = 'https://api.anthropic.com/v1'

    supports_web_search = True
    supports_code_interpreter = True

    reasoning_error_tokens = ('thinking', 'effort', 'output_config')

    # ----------------------------------------------------------
    # Functions
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
        inputs: list[dict],
        tools_schema: list[dict] | None = None,
        text_schema: dict | None = None,
        on_delta: Callable | None = None,
        model: str | None = None,
        enable_web_search: bool = False,
        enable_code_interpreter: bool = False,
        cache_key: str | None = None,
        reasoning_effort: str | None = None,
    ) -> dict:
        """Build and stream a Messages request.

        A rejected effort or thinking setting is retried once without it; a
        response schema constrains the answer on the models that take one.
        """
        model = self.model_for(model)
        caching = model.startswith('claude')
        system_text, messages, anchor = self._inputs_to_messages(inputs)
        max_tokens = self.provider.max_tokens or 4096
        body = {
            'model': model,
            'messages': messages,
            'max_tokens': max_tokens,
            'stream': True,
        }
        output = {}
        adaptive = not any(token in model for token in LEGACY_THINKING_MODEL_TOKENS)
        if any(token in model for token in THINKING_MODEL_TOKENS):
            if adaptive:
                body['thinking'] = {'type': 'adaptive'}
                if reasoning_effort:
                    output['effort'] = (
                        'low' if reasoning_effort == 'minimal' else reasoning_effort
                    )
            elif budget := LEGACY_THINKING_BUDGETS.get(reasoning_effort):
                body['max_tokens'] = max(max_tokens, budget + 1024)
                body['thinking'] = {'type': 'enabled', 'budget_tokens': budget}
        if text_schema and any(
            token in model for token in STRUCTURED_OUTPUT_MODEL_TOKENS
        ):
            output['format'] = {'type': 'json_schema', 'schema': text_schema['schema']}
        if system_text:
            body['system'] = (
                [{'type': 'text', 'text': system_text, 'cache_control': CACHE_CONTROL}]
                if caching
                else system_text
            )
        tools = [
            {'name': name, 'description': description, 'input_schema': parameters}
            for name, description, parameters in self._unique_tools(tools_schema)
        ]
        if enable_web_search:
            tools.append({'type': WEB_SEARCH_TOOL_TYPE, 'name': 'web_search'})
        if enable_code_interpreter:
            tools.append({'type': CODE_EXECUTION_TOOL_TYPE, 'name': 'code_execution'})
        if tools:
            if caching:
                tools[-1] = {**tools[-1], 'cache_control': CACHE_CONTROL}
            body['tools'] = tools
        if caching and anchor is not None:
            msg_index, block_index = anchor
            messages[msg_index]['content'][block_index]['cache_control'] = CACHE_CONTROL
        return self._invoke_with_reasoning_retry(
            model,
            lambda callback: self._stream(
                {**body, **({'output_config': output} if output else {})}, callback
            ),
            on_delta,
            ((output, ('effort',)) if adaptive else (body, ('thinking',)),),
        )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @classmethod
    def _inputs_to_messages(
        cls, inputs
    ) -> tuple[str, list[dict], tuple[int, int] | None]:
        """Convert canonical inputs into Anthropic system text, messages, and anchor.

        A turn carrying its Anthropic blocks replays them verbatim, as Anthropic
        validates its thinking; a lone carried thinking block still replays.
        The anchor is the ``(message, block)`` of the last non-volatile block.
        """
        messages = []
        anchor = None

        def append(role: str, block: dict, volatile: bool) -> None:
            """Append a block to the messages, anchoring it unless volatile."""
            nonlocal anchor
            cls._append_turn(messages, 'content', role, block)
            if not volatile:
                anchor = len(messages) - 1, len(messages[-1]['content']) - 1

        for item in inputs or []:
            role = item.get('role')
            volatile = bool(item.get('_cache_volatile'))
            if item.get('type') == 'function_call':
                arguments, _error = cls._parse_tool_arguments(item.get('arguments'))
                block = {
                    'type': 'tool_use',
                    'id': item.get('call_id'),
                    'name': item.get('name'),
                    'input': arguments,
                }
                append('assistant', block, volatile)
            elif item.get('type') == 'function_call_output':
                output = item.get('output')
                if not isinstance(output, str):
                    output = json.dumps(output, default=str)
                block = {
                    'type': 'tool_result',
                    'tool_use_id': item.get('call_id'),
                    'content': output,
                }
                append('user', block, volatile)
            elif role in ('user', 'assistant'):
                state = cls._carried_state(item)
                thinking = state.get('thinking') or []
                for block in state.get('blocks') or [
                    *(thinking if len(thinking) == 1 else []),
                    *cls._content_parts(item.get('content')),
                ]:
                    append(role, dict(block), volatile)
        return cls._system_text(inputs), messages, anchor

    @staticmethod
    def _text_part(text: str) -> dict:
        """Return the Anthropic text block carrying a text."""
        return {'type': 'text', 'text': text}

    @classmethod
    def _attachment_part(cls, block: dict) -> dict:
        """Convert an attachment block into an Anthropic image/document/text block."""
        mimetype = block.get('mimetype') or 'application/octet-stream'
        source = {
            'type': 'base64',
            'media_type': mimetype,
            'data': block.get('data_b64') or '',
        }
        if block.get('strategy') == 'image':
            return {'type': 'image', 'source': source}
        if block.get('strategy') == 'file' and mimetype == 'application/pdf':
            return {'type': 'document', 'source': source}
        return {'type': 'text', 'text': cls._attachment_text(block)}

    @staticmethod
    def _replayable_thinking(block: dict) -> dict | None:
        """Return the thinking block to replay verbatim, or ``None`` when there is none.

        Anthropic validates a thinking block against its own signature, so an
        unsigned one (a stream cut before ``signature_delta``) is dropped.
        """
        if block.get('type') == 'redacted_thinking':
            data = block.get('data')
            return {'type': 'redacted_thinking', 'data': data} if data else None
        thinking = block.get('thinking')
        signature = block.get('signature')
        if not thinking or not signature:
            return None
        return {'type': 'thinking', 'thinking': thinking, 'signature': signature}

    @classmethod
    def _assistant_carry(cls, content: list, blocks: list) -> list:
        """Return the assistant carry of a turn: one item, or none when it is empty.

        A turn with thinking or server tool blocks keeps all its Anthropic
        blocks in order in this provider's private state, to replay unchanged.
        """
        if not content and not blocks:
            return []
        carry = {'role': 'assistant', 'content': content}
        if all(block['type'] == 'text' for block in blocks):
            return [carry]
        return [cls._carry_state(carry, {'blocks': blocks})]

    @classmethod
    def _usage_from_anthropic(cls, usage: dict) -> dict:
        """Normalize Anthropic usage, folding cache tokens back into the total.

        Anthropic's ``input_tokens`` counts only the uncached prompt, so cache
        reads and writes are added back to recover the full prompt size the
        cost model and auto-compaction rely on.
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

    def _stream(self, body: dict, on_delta: Callable | None) -> dict:
        """Stream a Messages request, forwarding deltas, and assemble its result."""
        blocks, usage, meta = {}, {}, {}
        for event in self._post_stream('/messages', body):
            self._handle_stream_event(event, on_delta, blocks, usage, meta)
        text, calls, content, replay = [], [], [], []
        for index in sorted(blocks):
            block = blocks[index]
            if block['type'] in THINKING_BLOCK_TYPES:
                if thinking := self._replayable_thinking(block):
                    replay.append(thinking)
            elif block['type'] == 'text':
                if block['text']:
                    text.append(block['text'])
                    content.append({'type': 'output_text', 'text': block['text']})
                    replay.append(self._text_part(block['text']))
            elif block['type'] == 'tool_use':
                calls.append(
                    self._tool_call(
                        block['call_id'], block['name'], block['partial_json']
                    )
                )
            else:
                partial = block.pop('partial_json', '')
                replay.append(
                    {**block, **({'input': json.loads(partial)} if partial else {})}
                )
        return self._result(
            ''.join(text),
            calls,
            [*self._assistant_carry(content, replay), *map(self._call_item, calls)],
            self._usage_from_anthropic(usage),
            on_delta,
            meta.get('stop_reason') == 'max_tokens',
            body['max_tokens'],
        )

    def _handle_stream_event(
        self,
        event: dict,
        on_delta: Callable | None,
        blocks: dict,
        usage: dict,
        meta: dict,
    ) -> None:
        """Apply one streaming event to the accumulators and forward deltas.

        :param usage: collects the raw Anthropic token counts of the message
        :param meta: collects the final ``stop_reason``
        """
        kind = event.get('type') or ''
        if kind == 'message_start':
            start = (event.get('message') or {}).get('usage') or {}
            for key in (
                'input_tokens',
                'cache_read_input_tokens',
                'cache_creation_input_tokens',
            ):
                usage[key] = start.get(key, 0)
        elif kind == 'content_block_start':
            block = event.get('content_block') or {}
            if block.get('type') == 'text':
                blocks[event.get('index', 0)] = {'type': 'text', 'text': ''}
            elif block.get('type') in THINKING_BLOCK_TYPES:
                blocks[event.get('index', 0)] = {
                    'thinking': '',
                    'signature': '',
                    **block,
                }
            elif block.get('type') == 'tool_use':
                blocks[event.get('index', 0)] = {
                    'type': 'tool_use',
                    'call_id': block.get('id'),
                    'name': block.get('name'),
                    'partial_json': '',
                }
                self._call_on_delta(
                    on_delta,
                    'tool_start',
                    {'call_id': block.get('id'), 'name': block.get('name')},
                )
            elif block.get('type'):
                blocks[event.get('index', 0)] = {**block, 'partial_json': ''}
        elif kind == 'content_block_delta':
            entry = blocks.get(event.get('index', 0)) or {}
            delta = event.get('delta') or {}
            if delta.get('type') == 'text_delta' and entry.get('type') == 'text':
                if text := delta.get('text'):
                    entry['text'] += text
                    self._call_on_delta(on_delta, 'text', {'delta': text})
            elif (
                delta.get('type') == 'thinking_delta'
                and entry.get('type') == 'thinking'
            ):
                if text := delta.get('thinking'):
                    entry['thinking'] += text
                    self._call_on_delta(on_delta, 'reasoning', {'delta': text})
            elif (
                delta.get('type') == 'signature_delta'
                and entry.get('type') == 'thinking'
            ):
                entry['signature'] = (entry.get('signature') or '') + (
                    delta.get('signature') or ''
                )
            elif delta.get('type') == 'input_json_delta' and 'partial_json' in entry:
                if partial := delta.get('partial_json'):
                    entry['partial_json'] += partial
                    if entry['type'] == 'tool_use':
                        self._call_on_delta(
                            on_delta,
                            'tool_args',
                            {'call_id': entry['call_id'], 'delta': partial},
                        )
        elif kind == 'message_delta':
            if stop_reason := (event.get('delta') or {}).get('stop_reason'):
                meta['stop_reason'] = stop_reason
            if 'output_tokens' in (event.get('usage') or {}):
                usage['output_tokens'] = event['usage']['output_tokens']
        elif kind == 'error':
            self._raise_stream_error(event.get('error') or {})
