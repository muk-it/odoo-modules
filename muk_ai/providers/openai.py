from __future__ import annotations

from collections.abc import Callable

from odoo.addons.muk_ai.providers.base import ProviderBase

REASONING_MODEL_PREFIXES = ('o1', 'o3', 'o4', 'gpt-5')


class OpenAIProvider(ProviderBase):
    """OpenAI Responses API adapter with reasoning and streaming support."""

    name = 'openai'
    label = 'OpenAI'
    default_model = 'gpt-5-mini'
    default_url = 'https://api.openai.com/v1'

    supports_web_search = True
    supports_image_generation = True
    supports_code_interpreter = True

    reasoning_error_tokens = ('reasoning', 'effort')

    # ----------------------------------------------------------
    # Contract
    # ----------------------------------------------------------

    def headers(self) -> dict:
        """Return the OpenAI request headers with the bearer token."""
        return {
            'Authorization': f'Bearer {self.api_key}',
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
        """Build and run a Responses request, dispatching to streaming when requested."""
        model = self.model_for(model)
        body = {
            'model': model,
            'input': self._rewrite_attachments(inputs),
            'store': False,
        }
        if extra and (cache_key := extra.get('cache_key')):
            body['prompt_cache_key'] = cache_key
        if self.max_tokens:
            body['max_output_tokens'] = self.max_tokens
        effort = (extra or {}).get('reasoning_effort')
        if effort or self._supports_reasoning(model):
            body['reasoning'] = {'summary': 'detailed'}
            if effort:
                body['reasoning']['effort'] = effort
            body['include'] = ['reasoning.encrypted_content']
        if text_schema:
            body['text'] = {
                'format': {
                    'type': 'json_schema',
                    'name': text_schema.get('name', 'response'),
                    'schema': text_schema['schema'],
                    'strict': True,
                },
            }
        tools = list(tools_schema or [])
        if enable_web_search:
            tools.append({'type': 'web_search'})
        if enable_image_generation:
            tools.append({'type': 'image_generation'})
        if enable_code_interpreter:
            tools.append(
                {
                    'type': 'code_interpreter',
                    'container': {'type': 'auto'},
                }
            )
        if tools:
            body['tools'] = tools
            body['parallel_tool_calls'] = True
        return self._invoke_with_reasoning_retry(
            model,
            lambda callback: self._invoke(body, callback),
            on_delta,
            (
                (body.get('reasoning', {}), ('effort',)),
                (body, ('reasoning', 'include')),
            ),
        )

    # ----------------------------------------------------------
    # Reasoning
    # ----------------------------------------------------------

    def _invoke(self, body: dict, on_delta: Callable | None) -> dict:
        """Dispatch the request to the streaming or non-streaming path."""
        if callable(on_delta):
            return self._stream(body, on_delta)
        return self._parse_response(self._post_json('/responses', body))

    @staticmethod
    def _supports_reasoning(model: str) -> bool:
        """Return whether the model supports reasoning effort/summaries."""
        return any(model.startswith(prefix) for prefix in REASONING_MODEL_PREFIXES)

    # ----------------------------------------------------------
    # Attachments
    # ----------------------------------------------------------

    @classmethod
    def _rewrite_attachments(cls, inputs) -> list:
        """Rewrite attachment blocks to OpenAI form and drop thinking blocks."""
        rewritten = []
        for item in cls._strip_cache_markers(inputs):
            content = item.get('content') if isinstance(item, dict) else None
            if not isinstance(content, list):
                rewritten.append(item)
                continue
            new_content = []
            for block in content:
                if not isinstance(block, dict):
                    new_content.append(block)
                    continue
                block_type = block.get('type')
                if block_type == 'muk_ai_attachment':
                    new_content.append(cls._attachment_to_openai(block))
                elif block_type == 'muk_ai_thinking':
                    continue
                else:
                    new_content.append(block)
            rewritten.append({**item, 'content': new_content})
        return rewritten

    @staticmethod
    def _attachment_to_openai(block: dict) -> dict:
        """Convert an attachment block into an OpenAI input image/file/text block."""
        strategy = block.get('strategy')
        filename = block.get('filename') or 'attachment'
        mimetype = block.get('mimetype') or 'application/octet-stream'
        if strategy == 'image':
            return {
                'type': 'input_image',
                'image_url': f'data:{mimetype};base64,{block.get("data_b64", "")}',
            }
        if strategy == 'file':
            return {
                'type': 'input_file',
                'filename': filename,
                'file_data': f'data:{mimetype};base64,{block.get("data_b64", "")}',
            }
        text = block.get('inline_text') or ''
        prefix = f'--- File: {filename} ({mimetype}) ---\n'
        if block.get('truncated'):
            text += '\n[truncated]'
        return {'type': 'input_text', 'text': prefix + text}

    # ----------------------------------------------------------
    # Built-in tool output rendering
    # ----------------------------------------------------------

    @staticmethod
    def _render_image_call(item: dict) -> str:
        """Render an image-generation call result as a Markdown image, or ``''``."""
        if item.get('status') == 'failed':
            return ''
        result = (item.get('result') or '').strip()
        if not result:
            return ''
        url = (
            result
            if result.startswith(('data:', 'http'))
            else f'data:image/png;base64,{result}'
        )
        return f'\n\n![generated image]({url})\n\n'

    @staticmethod
    def _render_code_call(item: dict) -> str:
        """Render a code-interpreter call as Markdown code, logs, and file notes."""
        code = (item.get('code') or '').strip()
        parts = []
        if code:
            parts.append(f'```python\n{code}\n```')
        for entry in item.get('results') or []:
            entry_type = entry.get('type')
            if entry_type == 'logs':
                logs = (entry.get('logs') or '').strip()
                if logs:
                    parts.append(f'```\n{logs}\n```')
            elif entry_type == 'files':
                for f in entry.get('files') or []:
                    name = (f.get('name') or '').strip() or 'file'
                    parts.append(f'_(generated file: `{name}`)_')
        if not parts:
            return ''
        return '\n\n' + '\n\n'.join(parts) + '\n\n'

    # ----------------------------------------------------------
    # Parse
    # ----------------------------------------------------------

    def _parse_response(self, payload: dict) -> dict:
        """Parse a non-streaming response into text, tool calls, carry inputs, and usage."""
        output = payload.get('output') or []
        text_parts = []
        tool_calls = []
        carry_inputs = []
        for line in output:
            line_type = line.get('type')
            if line_type == 'function_call':
                args, parse_error = self._parse_tool_arguments(line.get('arguments'))
                tool_calls.append(
                    {
                        'call_id': line.get('call_id'),
                        'name': line.get('name'),
                        'arguments': args,
                        '_parse_error': parse_error,
                    }
                )
                carry_inputs.append(line)
            elif line_type == 'message':
                for content in line.get('content') or []:
                    if text := content.get('text'):
                        text_parts.append(text)
            elif line_type == 'image_generation_call':
                snippet = self._render_image_call(line)
                if snippet:
                    text_parts.append(snippet)
            elif line_type == 'code_interpreter_call':
                snippet = self._render_code_call(line)
                if snippet:
                    text_parts.append(snippet)
            elif text := line.get('text'):
                text_parts.append(text)
        usage = payload.get('usage') or {}
        result = {
            'text': '\n'.join(text_parts).strip(),
            'tool_calls': tool_calls,
            'carry_inputs': carry_inputs,
            'usage': self._usage(
                input_tokens=usage.get('input_tokens'),
                output_tokens=usage.get('output_tokens'),
                cache_read_tokens=(usage.get('input_tokens_details') or {}).get(
                    'cached_tokens'
                ),
            ),
        }
        if payload.get('status') == 'incomplete':
            reason = (payload.get('incomplete_details') or {}).get('reason')
            self._apply_truncation(
                result,
                limit=self.max_tokens if reason == 'max_output_tokens' else None,
            )
        return result

    # ----------------------------------------------------------
    # Streaming
    # ----------------------------------------------------------

    def _stream(self, body: dict, on_delta) -> dict:
        """Stream a Responses request, emitting deltas and assembling the final result."""
        body = {**body, 'stream': True}
        text_parts = []
        tool_calls_by_index = {}
        carry_inputs = []
        usage = {}
        truncation = None
        rendered_item_ids = set()
        image_b64_by_item = {}
        for event in self._post_stream('/responses', body):
            event_type = event.get('type') or ''
            if event_type == 'response.image_generation_call.partial_image':
                b64 = event.get('partial_image_b64')
                item_id = event.get('item_id')
                if b64 and item_id:
                    image_b64_by_item[item_id] = b64
                continue
            if event_type == 'response.image_generation_call.completed':
                item_id = event.get('item_id')
                b64 = image_b64_by_item.get(item_id)
                if b64 and item_id not in rendered_item_ids:
                    rendered_item_ids.add(item_id)
                    snippet = self._render_image_call(
                        {'status': 'completed', 'result': b64}
                    )
                    if snippet:
                        text_parts.append(snippet)
                        self._call_on_delta(on_delta, 'text', {'delta': snippet})
                continue
            if event_type == 'response.output_text.delta':
                delta = event.get('delta') or ''
                if not delta:
                    continue
                text_parts.append(delta)
                self._call_on_delta(on_delta, 'text', {'delta': delta})
            elif event_type == 'response.reasoning_summary_text.delta':
                delta = event.get('delta') or ''
                if delta:
                    self._call_on_delta(on_delta, 'reasoning', {'delta': delta})
            elif event_type == 'response.output_item.added':
                item = event.get('item') or {}
                if item.get('type') == 'function_call':
                    index = event.get('output_index', len(tool_calls_by_index))
                    tool_calls_by_index[index] = {
                        'call_id': item.get('call_id'),
                        'name': item.get('name'),
                        'arguments': '',
                    }
                    self._call_on_delta(
                        on_delta,
                        'tool_start',
                        {
                            'call_id': item.get('call_id'),
                            'name': item.get('name'),
                        },
                    )
            elif event_type == 'response.function_call_arguments.delta':
                index = event.get('output_index')
                entry = tool_calls_by_index.get(index)
                if entry is None:
                    continue
                delta = event.get('delta') or ''
                if not delta:
                    continue
                entry['arguments'] += delta
                self._call_on_delta(
                    on_delta,
                    'tool_args',
                    {
                        'call_id': entry['call_id'],
                        'delta': delta,
                    },
                )
            elif event_type == 'response.output_item.done':
                item = event.get('item') or {}
                item_type = item.get('type')
                if item_type == 'function_call':
                    index = event.get('output_index')
                    entry = tool_calls_by_index.get(index)
                    if entry is not None:
                        entry['arguments'] = item.get('arguments') or entry['arguments']
                        carry_inputs.append(item)
                elif item_type == 'reasoning':
                    carry_inputs.append(item)
                elif item_type == 'image_generation_call':
                    item_id = item.get('id')
                    if not item.get('result') and item_id in image_b64_by_item:
                        item = {**item, 'result': image_b64_by_item[item_id]}
                    snippet = self._render_image_call(item)
                    if snippet and item_id not in rendered_item_ids:
                        rendered_item_ids.add(item_id)
                        text_parts.append(snippet)
                        self._call_on_delta(on_delta, 'text', {'delta': snippet})
                elif item_type == 'code_interpreter_call':
                    snippet = self._render_code_call(item)
                    if snippet and item.get('id') not in rendered_item_ids:
                        rendered_item_ids.add(item.get('id'))
                        text_parts.append(snippet)
                        self._call_on_delta(on_delta, 'text', {'delta': snippet})
            elif event_type in ('response.completed', 'response.incomplete'):
                resp = event.get('response') or {}
                usage = resp.get('usage') or {}
                if event_type == 'response.incomplete':
                    truncation = resp.get('incomplete_details') or {}
                for item in resp.get('output') or []:
                    item_type = item.get('type')
                    if (
                        item_type == 'message'
                        and not any(c.get('type') == 'message' for c in carry_inputs)
                    ) or (
                        item_type == 'reasoning'
                        and not any(
                            c.get('type') == 'reasoning'
                            and c.get('id') == item.get('id')
                            for c in carry_inputs
                        )
                    ):
                        carry_inputs.append(item)
                    elif item_type == 'image_generation_call':
                        item_id = item.get('id')
                        if not item.get('result') and item_id in image_b64_by_item:
                            item = {**item, 'result': image_b64_by_item[item_id]}
                        snippet = self._render_image_call(item)
                        if snippet and item_id not in rendered_item_ids:
                            rendered_item_ids.add(item_id)
                            text_parts.append(snippet)
                            self._call_on_delta(on_delta, 'text', {'delta': snippet})
                    elif item_type == 'code_interpreter_call':
                        snippet = self._render_code_call(item)
                        if snippet and item.get('id') not in rendered_item_ids:
                            rendered_item_ids.add(item.get('id'))
                            text_parts.append(snippet)
                            self._call_on_delta(on_delta, 'text', {'delta': snippet})
            elif event_type in ('error', 'response.error', 'response.failed'):
                error = (
                    event.get('error')
                    or (event.get('response') or {}).get('error')
                    or {}
                )
                message = error.get('message') or 'Unknown streaming error'
                if code := error.get('code') or error.get('type'):
                    message = f'{message} (code: {code})'
                self._raise(message)

        tool_calls = []
        for entry in tool_calls_by_index.values():
            args, parse_error = self._parse_tool_arguments(entry['arguments'])
            tool_calls.append(
                {
                    'call_id': entry['call_id'],
                    'name': entry['name'],
                    'arguments': args,
                    '_parse_error': parse_error,
                }
            )
        result = {
            'text': ''.join(text_parts).strip(),
            'tool_calls': tool_calls,
            'carry_inputs': carry_inputs,
            'usage': self._usage(
                input_tokens=usage.get('input_tokens'),
                output_tokens=usage.get('output_tokens'),
                cache_read_tokens=(usage.get('input_tokens_details') or {}).get(
                    'cached_tokens'
                ),
            ),
        }
        if truncation is not None:
            self._apply_truncation(
                result,
                on_delta,
                self.max_tokens
                if truncation.get('reason') == 'max_output_tokens'
                else None,
            )
        return result
