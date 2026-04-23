from .base import ProviderBase


class OpenAIProvider(ProviderBase):

    name = 'openai'
    label = "OpenAI"
    default_model = 'gpt-5-mini'
    default_url = 'https://api.openai.com/v1'

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
        model = self.model_for(model)
        body = {
            'model': model,
            'input': self._rewrite_attachments(inputs),
            'store': False,
        }
        if self.max_tokens:
            body['max_output_tokens'] = self.max_tokens
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
            tools.append({
                'type': 'code_interpreter',
                'container': {'type': 'auto'},
            })
        if tools:
            body['tools'] = tools
            body['parallel_tool_calls'] = True
        if callable(on_delta):
            return self._stream(body, on_delta)
        return self._parse_response(self._post_json('/responses', body))

    # ----------------------------------------------------------
    # Attachments
    # ----------------------------------------------------------

    @classmethod
    def _rewrite_attachments(cls, inputs):
        rewritten = []
        for item in inputs or []:
            content = item.get('content') if isinstance(item, dict) else None
            if not isinstance(content, list):
                rewritten.append(item)
                continue
            new_content = []
            for block in content:
                if isinstance(block, dict) and block.get('type') == 'muk_ai_attachment':
                    new_content.append(cls._attachment_to_openai(block))
                else:
                    new_content.append(block)
            rewritten.append({**item, 'content': new_content})
        return rewritten

    @staticmethod
    def _attachment_to_openai(block):
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
    # Parse
    # ----------------------------------------------------------

    def _parse_response(self, payload):
        output = payload.get('output') or []
        text_parts = []
        tool_calls = []
        carry_inputs = []
        for line in output:
            line_type = line.get('type')
            if line_type == 'function_call':
                args, parse_error = self._parse_tool_arguments(line.get('arguments'))
                tool_calls.append({
                    'call_id': line.get('call_id'),
                    'name': line.get('name'),
                    'arguments': args,
                    '_parse_error': parse_error,
                })
                carry_inputs.append(line)
            elif line_type == 'message':
                for content in line.get('content') or []:
                    if text := content.get('text'):
                        text_parts.append(text)
            elif text := line.get('text'):
                text_parts.append(text)
        usage = payload.get('usage') or {}
        return {
            'text': '\n'.join(text_parts).strip(),
            'tool_calls': tool_calls,
            'carry_inputs': carry_inputs,
            'usage': self._usage(
                input_tokens=usage.get('input_tokens'),
                output_tokens=usage.get('output_tokens'),
                cached_tokens=(usage.get('input_tokens_details') or {}).get('cached_tokens'),
            ),
        }

    # ----------------------------------------------------------
    # Streaming
    # ----------------------------------------------------------

    def _stream(self, body, on_delta):
        body = {**body, 'stream': True}
        text_parts = []
        tool_calls_by_index = {}
        carry_inputs = []
        usage = {}
        for event in self._post_stream('/responses', body):
            event_type = event.get('type') or ''
            if event_type == 'response.output_text.delta':
                delta = event.get('delta') or ''
                if not delta:
                    continue
                text_parts.append(delta)
                self._call_on_delta(on_delta, 'text', {'delta': delta})
            elif event_type == 'response.output_item.added':
                item = event.get('item') or {}
                if item.get('type') == 'function_call':
                    index = event.get('output_index', len(tool_calls_by_index))
                    tool_calls_by_index[index] = {
                        'call_id': item.get('call_id'),
                        'name': item.get('name'),
                        'arguments': '',
                    }
                    self._call_on_delta(on_delta, 'tool_start', {
                        'call_id': item.get('call_id'),
                        'name': item.get('name'),
                    })
            elif event_type == 'response.function_call_arguments.delta':
                index = event.get('output_index')
                entry = tool_calls_by_index.get(index)
                if entry is None:
                    continue
                delta = event.get('delta') or ''
                if not delta:
                    continue
                entry['arguments'] += delta
                self._call_on_delta(on_delta, 'tool_args', {
                    'call_id': entry['call_id'],
                    'delta': delta,
                })
            elif event_type == 'response.output_item.done':
                item = event.get('item') or {}
                if item.get('type') == 'function_call':
                    index = event.get('output_index')
                    entry = tool_calls_by_index.get(index)
                    if entry is not None:
                        entry['arguments'] = item.get('arguments') or entry['arguments']
                        carry_inputs.append(item)
            elif event_type == 'response.completed':
                resp = event.get('response') or {}
                usage = resp.get('usage') or {}
                for item in resp.get('output') or []:
                    if item.get('type') == 'message' and not any(
                        c.get('type') == 'message' for c in carry_inputs
                    ):
                        carry_inputs.append(item)
            elif event_type == 'response.error':
                error = event.get('error') or {}
                self._raise(error.get('message') or 'Unknown streaming error')

        tool_calls = []
        for entry in tool_calls_by_index.values():
            args, parse_error = self._parse_tool_arguments(entry['arguments'])
            tool_calls.append({
                'call_id': entry['call_id'],
                'name': entry['name'],
                'arguments': args,
                '_parse_error': parse_error,
            })
        return {
            'text': ''.join(text_parts).strip(),
            'tool_calls': tool_calls,
            'carry_inputs': carry_inputs,
            'usage': self._usage(
                input_tokens=usage.get('input_tokens'),
                output_tokens=usage.get('output_tokens'),
                cached_tokens=(usage.get('input_tokens_details') or {}).get('cached_tokens'),
            ),
        }
