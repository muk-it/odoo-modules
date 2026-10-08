from __future__ import annotations

from collections.abc import Callable

from odoo.tools.translate import LazyTranslate

from odoo.addons.muk_ai.providers.base import ProviderBase
from odoo.addons.muk_ai.providers.region import CUSTOM, Region

_lt = LazyTranslate('muk_ai')

REASONING_MODEL_PREFIXES = ('o1', 'o3', 'o4', 'gpt-5', 'gpt-6')


class OpenAIProvider(ProviderBase):
    """OpenAI Responses API adapter with reasoning and streaming support."""

    name = 'openai'
    label = 'OpenAI'
    default_model = 'gpt-5.6-terra'
    default_url = 'https://api.openai.com/v1'
    regions = (
        Region('eu', _lt('Europe'), 'https://eu.api.openai.com/v1'),
        Region('us', _lt('United States'), 'https://us.api.openai.com/v1'),
        Region('mtls-eu', _lt('Europe (mTLS)'), 'https://mtls-eu.api.openai.com/v1'),
        CUSTOM,
    )

    supports_web_search = True
    supports_code_interpreter = True

    reasoning_error_tokens = ('reasoning', 'effort')

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    def headers(self) -> dict:
        """Return the OpenAI request headers with the bearer token."""
        return {
            'Authorization': f'Bearer {self.api_key}',
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
        """Build and stream a Responses request."""
        model = self.model_for(model)
        body = {
            'model': model,
            'input': self._rewrite_attachments(inputs),
            'store': False,
            'stream': True,
        }
        if cache_key:
            body['prompt_cache_key'] = cache_key
        if max_tokens := self.provider.max_tokens:
            body['max_output_tokens'] = max_tokens
        if reasoning_effort or model.startswith(REASONING_MODEL_PREFIXES):
            body['reasoning'] = {'summary': 'detailed'}
            if reasoning_effort:
                body['reasoning']['effort'] = reasoning_effort
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
        if enable_code_interpreter:
            tools.append({'type': 'code_interpreter', 'container': {'type': 'auto'}})
        if tools:
            body.update(tools=tools, parallel_tool_calls=True)
        return self._invoke_with_reasoning_retry(
            model,
            lambda callback: self._stream(body, callback),
            on_delta,
            (
                (body.get('reasoning', {}), ('effort',)),
                (body, ('reasoning', 'include')),
            ),
        )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @classmethod
    def _rewrite_attachments(cls, inputs) -> list:
        """Rewrite attachment blocks to their OpenAI form, dropping canonical-only ones.

        Canonical content blocks pass verbatim, so a ``muk_ai_`` block with no
        OpenAI counterpart is dropped here rather than sent to be rejected.
        """
        rewritten = []
        for item in cls._wire_items(inputs):
            content = item.get('content') if isinstance(item, dict) else None
            if not isinstance(content, list):
                rewritten.append(item)
                continue
            blocks = []
            for block in content:
                kind = block.get('type') or '' if isinstance(block, dict) else ''
                if kind == 'muk_ai_attachment':
                    blocks.append(cls._attachment_part(block))
                elif not kind.startswith('muk_ai_'):
                    blocks.append(block)
            rewritten.append({**item, 'content': blocks})
        return rewritten

    @classmethod
    def _attachment_part(cls, block: dict) -> dict:
        """Convert an attachment block into an OpenAI input image/file/text block."""
        mimetype = block.get('mimetype') or 'application/octet-stream'
        data = f'data:{mimetype};base64,{block.get("data_b64", "")}'
        if block.get('strategy') == 'image':
            return {'type': 'input_image', 'image_url': data}
        if block.get('strategy') == 'file':
            return {
                'type': 'input_file',
                'filename': block.get('filename') or 'attachment',
                'file_data': data,
            }
        return {'type': 'input_text', 'text': cls._attachment_text(block)}

    @staticmethod
    def _render_code_call(item: dict) -> str:
        """Render a code-interpreter call as Markdown code, logs, and file notes."""
        parts = []
        if code := (item.get('code') or '').strip():
            parts.append(f'```python\n{code}\n```')
        for entry in item.get('results') or []:
            if entry.get('type') == 'logs' and (
                logs := (entry.get('logs') or '').strip()
            ):
                parts.append(f'```\n{logs}\n```')
            elif entry.get('type') == 'files':
                for file in entry.get('files') or []:
                    name = (file.get('name') or '').strip() or 'file'
                    parts.append(f'_(generated file: `{name}`)_')
        return '\n\n' + '\n\n'.join(parts) + '\n\n' if parts else ''

    def _stream(self, body: dict, on_delta: Callable | None) -> dict:
        """Stream a Responses request, forwarding deltas, and assemble its result.

        Reasoning and function-call items are carried verbatim, as a stateless
        request has to replay them to the vendor.
        """
        text, calls, carry, rendered = [], {}, [], set()
        usage, truncated, limit = {}, False, None

        def render(item: dict) -> None:
            """Add a code-interpreter call to the answer once."""
            if item.get('id') not in rendered and (
                snippet := self._render_code_call(item)
            ):
                rendered.add(item.get('id'))
                text.append(snippet)
                self._call_on_delta(on_delta, 'text', {'delta': snippet})

        for event in self._post_stream('/responses', body):
            kind = event.get('type') or ''
            item = event.get('item') or {}
            if kind == 'response.output_text.delta' and (delta := event.get('delta')):
                text.append(delta)
                self._call_on_delta(on_delta, 'text', {'delta': delta})
            elif kind == 'response.reasoning_summary_text.delta' and (
                delta := event.get('delta')
            ):
                self._call_on_delta(on_delta, 'reasoning', {'delta': delta})
            elif (
                kind == 'response.output_item.added'
                and item.get('type') == 'function_call'
            ):
                calls[event.get('output_index', len(calls))] = {**item, 'arguments': ''}
                self._call_on_delta(
                    on_delta,
                    'tool_start',
                    {'call_id': item.get('call_id'), 'name': item.get('name')},
                )
            elif kind == 'response.function_call_arguments.delta':
                if (entry := calls.get(event.get('output_index'))) and (
                    delta := event.get('delta')
                ):
                    entry['arguments'] += delta
                    self._call_on_delta(
                        on_delta,
                        'tool_args',
                        {'call_id': entry.get('call_id'), 'delta': delta},
                    )
            elif kind == 'response.output_item.done':
                if item.get('type') == 'function_call':
                    if entry := calls.get(event.get('output_index')):
                        entry['arguments'] = item.get('arguments') or entry['arguments']
                        carry.append(item)
                elif item.get('type') == 'reasoning':
                    carry.append(item)
                elif item.get('type') == 'code_interpreter_call':
                    render(item)
            elif kind in ('response.completed', 'response.incomplete'):
                response = event.get('response') or {}
                usage = response.get('usage') or {}
                if kind == 'response.incomplete':
                    truncated = True
                    reason = (response.get('incomplete_details') or {}).get('reason')
                    if reason == 'max_output_tokens':
                        limit = self.provider.max_tokens
                for output in response.get('output') or []:
                    if output.get('type') == 'code_interpreter_call':
                        render(output)
                    elif output.get('type') == 'message':
                        if not any(c.get('type') == 'message' for c in carry):
                            carry.append(output)
                    elif output.get('type') == 'reasoning':
                        if not any(c.get('id') == output.get('id') for c in carry):
                            carry.append(output)
            elif kind in ('error', 'response.error', 'response.failed'):
                response = event.get('response') or {}
                self._raise_stream_error(
                    event.get('error') or response.get('error') or {}, 'code', 'type'
                )
        return self._result(
            ''.join(text),
            [
                self._tool_call(
                    entry.get('call_id'), entry.get('name'), entry['arguments']
                )
                for entry in calls.values()
            ],
            carry,
            self._usage(
                input_tokens=usage.get('input_tokens'),
                output_tokens=usage.get('output_tokens'),
                cache_read_tokens=(usage.get('input_tokens_details') or {}).get(
                    'cached_tokens'
                ),
            ),
            on_delta,
            truncated,
            limit,
        )
