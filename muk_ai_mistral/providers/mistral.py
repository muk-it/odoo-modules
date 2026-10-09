from __future__ import annotations

import base64
import json
from collections.abc import Callable

import requests

from odoo.exceptions import UserError
from odoo.tools.mimetypes import guess_mimetype

from odoo.addons.muk_ai.providers.base import ProviderBase

PROTECTED_TOOL_NAMES = frozenset(
    {
        'code_interpreter',
        'edit_image',
        'generate_image',
        'library_search',
        'news_search',
        'web_search',
    }
)
TOOL_NAME_PREFIX = 'muk_ai_'
IMAGE_INSTRUCTIONS = (
    'Call the image_generation tool exactly once to render the request as one '
    'image, then stop. Do not describe the image and do not answer with text.'
)


class MistralProvider(ProviderBase):
    """Mistral's stateless Conversations API with its built-in connectors."""

    name = 'mistral'
    label = 'Mistral AI'
    default_model = 'mistral-medium-latest'
    default_url = 'https://api.mistral.ai/v1'

    supports_web_search = True
    supports_code_interpreter = True

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    def headers(self) -> dict:
        """Return the bearer-authenticated JSON request headers."""
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
        """Build and stream a Conversations request."""
        body = {
            'model': self.model_for(model),
            'inputs': self._entries(inputs),
            'store': False,
            'stream': True,
        }
        if instructions := self._system_text(inputs):
            body['instructions'] = instructions
        args = body['completion_args'] = {}
        if max_tokens := self.provider.max_tokens:
            args['max_tokens'] = max_tokens
        if text_schema:
            args['response_format'] = {
                'type': 'json_schema',
                'json_schema': {
                    'name': text_schema.get('name', 'response'),
                    'schema': text_schema['schema'],
                    'strict': True,
                },
            }
        tools = [
            {
                'type': 'function',
                'function': {
                    'name': self._wire_name(name),
                    'description': description,
                    'parameters': parameters,
                },
            }
            for name, description, parameters in self._unique_tools(tools_schema)
        ]
        tools += [
            {'type': kind}
            for kind, enabled in (
                ('web_search', enable_web_search),
                ('code_interpreter', enable_code_interpreter),
            )
            if enabled
        ]
        if tools:
            body['tools'] = tools
        return self._stream(body, on_delta)

    def generate_image(
        self,
        model: str,
        prompt: str,
        options: dict | None = None,
    ) -> dict:
        """Render one image with a chat model driving the image connector.

        The options have no equivalent there and are not sent.

        :raise UserError: when the request or download fails or no image comes back
        """
        payload = self._post_json(
            '/conversations',
            {
                'model': model,
                'instructions': IMAGE_INSTRUCTIONS,
                'inputs': [self._entry('message.input', role='user', content=prompt)],
                'tools': [{'type': 'image_generation'}],
                'store': False,
            },
            timeout=self.provider.image_timeout,
        )
        execution = next(
            (
                entry.get('info') or {}
                for entry in payload.get('outputs') or []
                if entry.get('type') == 'tool.execution'
            ),
            {},
        )
        if not (url := json.loads(execution.get('result') or '{}').get('url')):
            self._raise(self.env._('the model answered with text instead of an image'))
        mimetype, data_b64 = self._download(url)
        return {
            'data_b64': data_b64,
            'mimetype': mimetype,
            'revised_prompt': '',
            'usage': {'images': 1},
        }

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @staticmethod
    def _wire_name(name: str) -> str:
        """Prefix a tool name Mistral reserves for its own connectors.

        A function called ``web_search`` or ``generate_image`` is rejected
        with ``422 protected function name``.
        """
        return f'{TOOL_NAME_PREFIX}{name}' if name in PROTECTED_TOOL_NAMES else name

    @staticmethod
    def _muk_name(name: str) -> str:
        """Restore the name of a tool sent under the protection prefix."""
        stripped = name.removeprefix(TOOL_NAME_PREFIX)
        return stripped if stripped in PROTECTED_TOOL_NAMES else name

    @staticmethod
    def _entry(kind: str, **values) -> dict:
        """Return a Conversations entry of the given type."""
        return {'object': 'entry', 'type': kind, **values}

    @staticmethod
    def _json(value) -> str:
        """Return a value as the JSON text the wire expects, a string as it is."""
        return value if isinstance(value, str) else json.dumps(value, default=str)

    def _entries(self, inputs) -> list[dict]:
        """Convert canonical inputs, the system items aside, into entries."""
        entries = []
        for item in inputs or []:
            kind, role = item.get('type'), item.get('role')
            if kind == 'function_call':
                entries.append(
                    self._entry(
                        'function.call',
                        tool_call_id=item.get('call_id') or '',
                        name=self._wire_name(item.get('name') or ''),
                        arguments=self._json(item.get('arguments') or '{}'),
                    )
                )
            elif kind == 'function_call_output':
                entries.append(
                    self._entry(
                        'function.result',
                        tool_call_id=item.get('call_id') or '',
                        result=self._json(item.get('output')),
                    )
                )
            elif role == 'user':
                entries.append(
                    self._entry(
                        'message.input',
                        role='user',
                        content=self._content_parts(item.get('content')),
                    )
                )
            elif role == 'assistant':
                entries.append(
                    self._entry(
                        'message.output',
                        role='assistant',
                        content=self._text_from_content(item.get('content')),
                    )
                )
        return entries

    @staticmethod
    def _text_part(text: str) -> dict:
        """Return the Mistral chunk carrying a text."""
        return {'type': 'text', 'text': text}

    @classmethod
    def _attachment_part(cls, block: dict) -> dict:
        """Convert an attachment block into an image, document or text chunk."""
        mimetype = block.get('mimetype') or 'application/octet-stream'
        data = f'data:{mimetype};base64,{block.get("data_b64") or ""}'
        if block.get('strategy') == 'image':
            return {'type': 'image_url', 'image_url': data}
        if block.get('strategy') == 'file':
            return {'type': 'document_url', 'document_url': data}
        return cls._text_part(cls._attachment_text(block))

    def _download(self, url: str, headers: dict | None = None) -> tuple[str, str]:
        """Fetch a generated file and return its sniffed mimetype and base64 content.

        :raise UserError: when the download fails
        """
        try:
            response = self._http_session().get(
                url, headers=headers, timeout=self.provider.request_timeout
            )
            response.raise_for_status()
        except requests.RequestException as error:
            self._raise(error)
        return (
            guess_mimetype(response.content, default='application/octet-stream'),
            base64.b64encode(response.content).decode('ascii'),
        )

    def _file_snippet(self, chunk: dict) -> str:
        """Render a generated file as an inline image, a note when it cannot load."""
        name = chunk.get('file_name') or 'image'
        try:
            mimetype, data_b64 = self._download(
                f'{self.api_url}/files/{chunk["file_id"]}/content', self.headers()
            )
        except UserError:
            return f'\n\n_(generated file: `{name}`)_\n\n'
        return f'\n\n![{name}](data:{mimetype};base64,{data_b64})\n\n'

    @staticmethod
    def _code_snippet(info: dict) -> str:
        """Render a code interpreter run as Markdown code and output blocks."""
        parts = [
            f'```{fence}\n{text}\n```'
            for fence, key in (('python', 'code'), ('', 'code_output'))
            if (text := (info.get(key) or '').strip())
        ]
        return '\n\n' + '\n\n'.join(parts) + '\n\n' if parts else ''

    def _stream(self, body: dict, on_delta: Callable | None) -> dict:
        """Stream a Conversations request and assemble its result.

        Generated files are downloaded once the stream ends. The wire reports
        no finish reason, so an answer that used the whole output budget is
        taken as cut at the cap.
        """
        text, calls, files, usage = [], {}, [], {}

        def emit(snippet: str) -> None:
            """Add a snippet to the answer and forward it."""
            if snippet:
                text.append(snippet)
                self._call_on_delta(on_delta, 'text', {'delta': snippet})

        for event in self._post_stream('/conversations', body):
            kind = event.get('type') or ''
            content = event.get('content')
            if kind == 'message.output.delta' and isinstance(content, str):
                emit(content)
            elif kind == 'message.output.delta' and isinstance(content, dict):
                if content.get('type') == 'thinking':
                    thought = self._text_from_content(content.get('thinking'))
                    self._call_on_delta(on_delta, 'reasoning', {'delta': thought})
                elif content.get('type') == 'tool_file':
                    files.append(content)
                elif url := content.get('url'):
                    emit(f' ([{content.get("title") or url}]({url}))')
            elif kind == 'tool.execution.done':
                emit(self._code_snippet(event.get('info') or {}))
            elif kind == 'function.call.delta':
                self._call_event(event, calls, on_delta)
            elif kind == 'conversation.response.done':
                usage = event.get('usage') or {}
            elif kind in ('conversation.response.error', 'error'):
                self._raise_stream_error(event, 'code')
        for chunk in files:
            emit(self._file_snippet(chunk))
        tool_calls = [
            self._tool_call(entry['call_id'], entry['name'], entry['arguments'])
            for entry in calls.values()
        ]
        answer = ''.join(text)
        carry = [self._text_carry(answer)] if answer.strip() else []
        limit = self.provider.max_tokens
        output_tokens = usage.get('completion_tokens') or 0
        return self._result(
            answer,
            tool_calls,
            carry + [self._call_item(call) for call in tool_calls],
            self._usage(usage.get('prompt_tokens'), output_tokens),
            on_delta,
            bool(limit) and output_tokens >= limit,
            limit,
        )

    def _call_event(self, event: dict, calls: dict, on_delta: Callable | None) -> None:
        """Fold a function call delta into its entry, forwarding the deltas."""
        entry = calls.setdefault(
            event.get('output_index', len(calls)),
            {'call_id': '', 'name': '', 'arguments': ''},
        )
        entry['call_id'] = event.get('tool_call_id') or entry['call_id']
        if not entry['name'] and (name := event.get('name')):
            entry['name'] = self._muk_name(name)
            self._call_on_delta(
                on_delta,
                'tool_start',
                {'call_id': entry['call_id'], 'name': entry['name']},
            )
        if arguments := event.get('arguments'):
            entry['arguments'] += arguments
            self._call_on_delta(
                on_delta,
                'tool_args',
                {'call_id': entry['call_id'], 'delta': arguments},
            )
