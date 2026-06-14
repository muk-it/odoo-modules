import base64
import json

import requests

from odoo.exceptions import UserError

from odoo.addons.muk_ai.providers.base import ProviderBase

WEB_SEARCH_TOOL = 'web_search'
CODE_INTERPRETER_TOOL = 'code_interpreter'
IMAGE_GENERATION_TOOL = 'image_generation'

STREAM_ATTEMPTS = 2
REQUEST_ATTEMPTS = 3


class MistralProvider(ProviderBase):

    name = 'mistral'
    label = "Mistral AI"
    default_model = 'mistral-medium-latest'
    default_url = 'https://api.mistral.ai/v1'

    supports_web_search = True
    supports_image_generation = True
    supports_code_interpreter = True

    # ----------------------------------------------------------
    # Contract
    # ----------------------------------------------------------

    def headers(self):
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
    ):
        instructions, entries = self._inputs_to_entries(inputs)
        body = {
            'model': self.model_for(model),
            'inputs': entries,
            'store': False,
        }
        if instructions:
            body['instructions'] = instructions
        completion_args = {}
        if self.max_tokens:
            completion_args['max_tokens'] = self.max_tokens
        if text_schema:
            completion_args['response_format'] = {
                'type': 'json_schema',
                'json_schema': {
                    'name': text_schema.get('name', 'response'),
                    'schema': text_schema['schema'],
                    'strict': True,
                },
            }
        if completion_args:
            body['completion_args'] = completion_args
        tools = self._tools_to_mistral(tools_schema)
        if enable_web_search:
            tools.append({'type': WEB_SEARCH_TOOL})
        if enable_code_interpreter:
            tools.append({'type': CODE_INTERPRETER_TOOL})
        if enable_image_generation:
            tools.append({'type': IMAGE_GENERATION_TOOL})
        if tools:
            body['tools'] = tools
        connectors = (
            enable_web_search
            or enable_image_generation
            or enable_code_interpreter
        )
        if callable(on_delta) and not connectors:
            return self._stream_request(body, on_delta)
        result = self._buffered_request(body)
        if callable(on_delta):
            self._emit_text(on_delta, result)
        return result

    # ----------------------------------------------------------
    # Inputs
    # ----------------------------------------------------------

    @classmethod
    def _inputs_to_entries(cls, inputs):
        system_parts = []
        entries = []
        for item in inputs or []:
            item_type = item.get('type')
            role = item.get('role')
            if role == 'system':
                text = cls._text_from_content(item.get('content'))
                if text:
                    system_parts.append(text)
                continue
            if item_type == 'function_call':
                arguments = item.get('arguments') or '{}'
                if not isinstance(arguments, str):
                    arguments = json.dumps(arguments, default=str)
                entries.append({
                    'object': 'entry',
                    'type': 'function.call',
                    'tool_call_id': item.get('call_id') or '',
                    'name': item.get('name') or '',
                    'arguments': arguments,
                })
                continue
            if item_type == 'function_call_output':
                output = item.get('output')
                if not isinstance(output, str):
                    output = json.dumps(output, default=str)
                entries.append({
                    'object': 'entry',
                    'type': 'function.result',
                    'tool_call_id': item.get('call_id') or '',
                    'result': output,
                })
                continue
            if role == 'user':
                entries.append({
                    'object': 'entry',
                    'type': 'message.input',
                    'role': 'user',
                    'content': cls._user_content_to_mistral(item.get('content')),
                })
                continue
            if role == 'assistant':
                text = cls._text_from_content(item.get('content'))
                entries.append({
                    'object': 'entry',
                    'type': 'message.output',
                    'role': 'assistant',
                    'content': text,
                })
        return '\n\n'.join(system_parts), entries

    @staticmethod
    def _text_from_content(content):
        if isinstance(content, str):
            return content
        parts = []
        for chunk in content or []:
            if isinstance(chunk, dict) and chunk.get('text'):
                parts.append(chunk['text'])
        return '\n\n'.join(parts)

    @classmethod
    def _user_content_to_mistral(cls, content):
        if isinstance(content, str):
            return content
        if not content:
            return ''
        text_parts = []
        multimodal = []
        for chunk in content:
            if not isinstance(chunk, dict):
                continue
            if chunk.get('type') == 'muk_ai_attachment':
                part = cls._attachment_to_part(chunk)
                if part is None:
                    continue
                if part.get('type') == 'image_url':
                    multimodal.append(part)
                else:
                    text_parts.append(part.get('text') or '')
            elif chunk.get('text'):
                text_parts.append(chunk['text'])
        if multimodal:
            result = list(multimodal)
            if text_parts:
                result.insert(0, {'type': 'text', 'text': '\n\n'.join(text_parts)})
            return result
        return '\n\n'.join(text_parts)

    @staticmethod
    def _attachment_to_part(block):
        strategy = block.get('strategy')
        mimetype = block.get('mimetype') or 'application/octet-stream'
        data_b64 = block.get('data_b64') or ''
        filename = block.get('filename') or 'attachment'
        if strategy == 'image' and data_b64:
            return {
                'type': 'image_url',
                'image_url': f'data:{mimetype};base64,{data_b64}',
            }
        text = block.get('inline_text') or ''
        prefix = f'--- File: {filename} ({mimetype}) ---\n'
        if block.get('truncated'):
            text += '\n[truncated]'
        if not text:
            return None
        return {'type': 'text', 'text': prefix + text}

    @staticmethod
    def _tools_to_mistral(tools_schema):
        if not tools_schema:
            return []
        seen = set()
        out = []
        for tool in tools_schema:
            name = tool.get('name')
            if not name or name in seen:
                continue
            seen.add(name)
            out.append({
                'type': 'function',
                'function': {
                    'name': name,
                    'description': tool.get('description') or '',
                    'parameters': tool.get('parameters') or {
                        'type': 'object', 'properties': {},
                    },
                },
            })
        return out

    # ----------------------------------------------------------
    # Parse
    # ----------------------------------------------------------

    def _parse_response(self, payload):
        text_parts = []
        message_text_parts = []
        tool_calls = []
        function_call_carries = []
        for entry in payload.get('outputs') or []:
            entry_type = entry.get('type')
            if entry_type == 'message.output':
                self._consume_message_content(
                    entry.get('content'), text_parts, message_text_parts,
                )
            elif entry_type == 'tool.execution':
                snippet = self._render_tool_execution(entry)
                if snippet:
                    text_parts.append(snippet)
                    message_text_parts.append(snippet)
            elif entry_type == 'function.call':
                self._consume_function_call(entry, tool_calls, function_call_carries)
        carry_inputs = []
        if message_text_parts:
            carry_inputs.append(self._assistant_text_carry(''.join(message_text_parts)))
        carry_inputs.extend(function_call_carries)
        usage = payload.get('usage') or {}
        return {
            'text': ''.join(text_parts).strip(),
            'tool_calls': tool_calls,
            'carry_inputs': carry_inputs,
            'usage': self._usage(
                input_tokens=usage.get('prompt_tokens'),
                output_tokens=usage.get('completion_tokens'),
            ),
        }

    def _consume_message_content(self, content, text_parts, message_text_parts):
        if isinstance(content, str):
            if content:
                text_parts.append(content)
                message_text_parts.append(content)
            return
        for chunk in content or []:
            if not isinstance(chunk, dict):
                continue
            snippet = self._render_chunk(chunk)
            if snippet:
                text_parts.append(snippet)
                message_text_parts.append(snippet)

    def _render_chunk(self, chunk):
        chunk_type = chunk.get('type')
        if chunk_type == 'text':
            return chunk.get('text') or ''
        if chunk_type == 'tool_reference':
            title = chunk.get('title') or chunk.get('url') or 'source'
            url = chunk.get('url') or ''
            return f' ([{title}]({url}))' if url else ''
        if chunk_type == 'tool_file':
            return self._render_tool_file(chunk)
        return ''

    def _render_tool_file(self, chunk):
        file_id = chunk.get('file_id')
        if not file_id:
            return ''
        file_type = (chunk.get('file_type') or 'png').lstrip('.')
        data_uri = self._download_file(file_id, file_type)
        name = chunk.get('file_name') or 'image'
        if data_uri:
            return f'\n\n![{name}]({data_uri})\n\n'
        return f'\n\n_(generated file: `{name}`)_\n\n'

    @staticmethod
    def _render_tool_execution(entry):
        info = entry.get('info') or {}
        parts = []
        code = (info.get('code') or '').strip()
        if code:
            parts.append(f'```python\n{code}\n```')
        output = (info.get('code_output') or '').strip()
        if output:
            parts.append(f'```\n{output}\n```')
        if not parts:
            return ''
        return '\n\n' + '\n\n'.join(parts) + '\n\n'

    def _consume_function_call(self, entry, tool_calls, function_call_carries):
        call_id = entry.get('tool_call_id') or entry.get('id') or ''
        name = entry.get('name') or ''
        raw_args = entry.get('arguments')
        if raw_args is None:
            raw_args = '{}'
        args, parse_error = self._parse_tool_arguments(raw_args)
        tool_calls.append({
            'call_id': call_id,
            'name': name,
            'arguments': args,
            '_parse_error': parse_error,
        })
        function_call_carries.append({
            'type': 'function_call',
            'name': name,
            'arguments': raw_args if isinstance(raw_args, str) else json.dumps(args, default=str),
            'call_id': call_id,
        })

    @staticmethod
    def _assistant_text_carry(text):
        return {
            'role': 'assistant',
            'content': [{'type': 'output_text', 'text': text}],
        }

    # ----------------------------------------------------------
    # Files
    # ----------------------------------------------------------

    def _download_file(self, file_id, file_type):
        try:
            response = requests.get(
                f'{self.api_url}/files/{file_id}/content',
                headers=self.headers(),
                timeout=self.request_timeout,
            )
            response.raise_for_status()
        except requests.RequestException:
            return None
        mimetype = f'image/{file_type}' if file_type else 'application/octet-stream'
        encoded = base64.b64encode(response.content).decode('ascii')
        return f'data:{mimetype};base64,{encoded}'

    # ----------------------------------------------------------
    # Streaming
    # ----------------------------------------------------------

    def _buffered_request(self, body):
        error = None
        for attempt in range(REQUEST_ATTEMPTS):
            try:
                return self._parse_response(self._post_json('/conversations', body))
            except UserError as exc:
                error = exc
        raise error

    def _emit_text(self, on_delta, result):
        if result.get('text'):
            self._call_on_delta(on_delta, 'text', {'delta': result['text']})

    def _stream_request(self, body, on_delta):
        progress = {'emitted': False}
        for attempt in range(STREAM_ATTEMPTS):
            try:
                return self._stream(body, on_delta, progress)
            except UserError:
                if progress['emitted']:
                    raise
        result = self._buffered_request(body)
        self._emit_text(on_delta, result)
        return result

    def _stream(self, body, on_delta, progress):
        body = {**body, 'stream': True}

        def tracked(kind, payload):
            progress['emitted'] = True
            on_delta(kind, payload)

        state = {
            'text': [],
            'tool_calls': {},
            'tool_files': [],
            'usage': self._usage(),
        }
        for event in self._post_stream('/conversations', body):
            self._handle_stream_event(event, state, tracked)

        text = ''.join(state['text'])
        for chunk in state['tool_files']:
            snippet = self._render_tool_file(chunk)
            if snippet:
                text += snippet
                self._call_on_delta(tracked, 'text', {'delta': snippet})

        tool_calls = []
        function_call_carries = []
        for index in sorted(state['tool_calls']):
            entry = state['tool_calls'][index]
            args, parse_error = self._parse_tool_arguments(
                entry.get('arguments') or '{}',
            )
            tool_calls.append({
                'call_id': entry.get('call_id') or '',
                'name': entry.get('name') or '',
                'arguments': args,
                '_parse_error': parse_error,
            })
            function_call_carries.append({
                'type': 'function_call',
                'name': entry.get('name') or '',
                'arguments': json.dumps(args, default=str),
                'call_id': entry.get('call_id') or '',
            })

        carry_inputs = []
        if text.strip():
            carry_inputs.append(self._assistant_text_carry(text))
        carry_inputs.extend(function_call_carries)
        return {
            'text': text.strip(),
            'tool_calls': tool_calls,
            'carry_inputs': carry_inputs,
            'usage': state['usage'],
        }

    def _handle_stream_event(self, event, state, on_delta):
        event_type = event.get('type') or ''
        if event_type == 'message.output.delta':
            content = event.get('content')
            if isinstance(content, str):
                if content:
                    state['text'].append(content)
                    self._call_on_delta(on_delta, 'text', {'delta': content})
            elif isinstance(content, dict):
                if content.get('type') == 'tool_file':
                    state['tool_files'].append(content)
                else:
                    snippet = self._render_chunk(content)
                    if snippet:
                        state['text'].append(snippet)
                        self._call_on_delta(on_delta, 'text', {'delta': snippet})
        elif event_type == 'tool.execution.done':
            snippet = self._render_tool_execution(event)
            if snippet:
                state['text'].append(snippet)
                self._call_on_delta(on_delta, 'text', {'delta': snippet})
        elif event_type == 'function.call.delta':
            self._accumulate_function_call(event, state, on_delta)
        elif event_type == 'function.call':
            self._accumulate_function_call(event, state, on_delta, complete=True)
        elif event_type == 'conversation.response.done':
            usage = event.get('usage') or {}
            state['usage'] = self._usage(
                input_tokens=usage.get('prompt_tokens'),
                output_tokens=usage.get('completion_tokens'),
            )
        elif event_type in ('conversation.response.error', 'error'):
            error = event.get('error') or event.get('message') or 'Unknown streaming error'
            if isinstance(error, dict):
                error = error.get('message') or 'Unknown streaming error'
            self._raise(error)

    def _accumulate_function_call(self, event, state, on_delta, complete=False):
        index = event.get('output_index', len(state['tool_calls']))
        entry = state['tool_calls'].setdefault(index, {
            'call_id': '',
            'name': '',
            'arguments': '',
        })
        call_id = event.get('tool_call_id') or event.get('id')
        if call_id:
            entry['call_id'] = call_id
        name = event.get('name')
        if name and not entry['name']:
            entry['name'] = name
            self._call_on_delta(on_delta, 'tool_start', {
                'call_id': entry['call_id'], 'name': entry['name'],
            })
        arguments = event.get('arguments')
        if arguments:
            if not isinstance(arguments, str):
                arguments = json.dumps(arguments, default=str)
            if complete:
                entry['arguments'] = arguments
            else:
                entry['arguments'] += arguments
            self._call_on_delta(on_delta, 'tool_args', {
                'call_id': entry['call_id'], 'delta': arguments,
            })
