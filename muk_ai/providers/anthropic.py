import json

from odoo.exceptions import UserError

from .base import ProviderBase

ANTHROPIC_VERSION = '2023-06-01'
WEB_SEARCH_TOOL_TYPE = 'web_search_20250305'
CODE_EXECUTION_TOOL_TYPE = 'code_execution_20250825'

THINKING_MODEL_TOKENS = (
    'opus-4', 'sonnet-4', '3-7-sonnet'
)
LEGACY_THINKING_MODEL_TOKENS = (
    'opus-4-0', 'opus-4-1', 'opus-4-5', 'opus-4-6',
    '3-7-sonnet', 'sonnet-4-0', 'sonnet-4-5', 'sonnet-4-6',
)
THINKING_BUDGET_TOKENS = 1024
ADAPTIVE_THINKING_EFFORT = 'medium'


class AnthropicProvider(ProviderBase):

    name = 'anthropic'
    label = "Anthropic"
    default_model = 'claude-sonnet-4-5'
    default_url = 'https://api.anthropic.com/v1'

    supports_web_search = True
    supports_image_generation = False
    supports_code_interpreter = True

    # ----------------------------------------------------------
    # Contract
    # ----------------------------------------------------------

    def headers(self):
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
    ):
        model = self.model_for(model)
        system_text, messages = self._inputs_to_messages(inputs)
        max_tokens = self.max_tokens or 4096
        body = {
            'model': model,
            'messages': messages,
            'max_tokens': max_tokens,
        }
        if self._supports_thinking(model):
            if self._uses_adaptive_thinking(model):
                body['thinking'] = {'type': 'adaptive'}
                body['output_config'] = {'effort': ADAPTIVE_THINKING_EFFORT}
            else:
                if max_tokens <= THINKING_BUDGET_TOKENS:
                    body['max_tokens'] = THINKING_BUDGET_TOKENS + 1024
                body['thinking'] = {
                    'type': 'enabled',
                    'budget_tokens': THINKING_BUDGET_TOKENS,
                }
        if system_text:
            body['system'] = system_text
        tools = self._tools_to_anthropic(tools_schema)
        if enable_web_search:
            tools.append({
                'type': WEB_SEARCH_TOOL_TYPE,
                'name': 'web_search',
            })
        if enable_code_interpreter:
            tools.append({
                'type': CODE_EXECUTION_TOOL_TYPE,
                'name': 'code_execution',
            })
        if tools:
            body['tools'] = tools
        try:
            return self._invoke(body, on_delta)
        except UserError as exc:
            if 'thinking' not in body or 'thinking' not in str(exc).lower():
                raise
            body.pop('thinking', None)
            body.pop('output_config', None)
            return self._invoke(body, on_delta)

    # ----------------------------------------------------------
    # Thinking
    # ----------------------------------------------------------

    def _invoke(self, body, on_delta):
        if callable(on_delta):
            return self._stream(body, on_delta)
        return self._parse_response(self._post_json('/messages', body))

    @staticmethod
    def _supports_thinking(model):
        return any(token in model for token in THINKING_MODEL_TOKENS)

    @staticmethod
    def _uses_adaptive_thinking(model):
        return not any(token in model for token in LEGACY_THINKING_MODEL_TOKENS)

    # ----------------------------------------------------------
    # Inputs
    # ----------------------------------------------------------

    @staticmethod
    def _text_from_content(content):
        if isinstance(content, str):
            return content
        parts = []
        for chunk in content or []:
            text = chunk.get('text')
            if text:
                parts.append(text)
        return ''.join(parts)

    @classmethod
    def _inputs_to_messages(cls, inputs):
        system_parts = []
        messages = []

        def append(role, block):
            if messages and messages[-1]['role'] == role:
                messages[-1]['content'].append(block)
            else:
                messages.append({'role': role, 'content': [block]})

        for item in inputs or []:
            item_type = item.get('type')
            role = item.get('role')
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
                append('assistant', {
                    'type': 'tool_use',
                    'id': item.get('call_id'),
                    'name': item.get('name'),
                    'input': arguments,
                })
                continue
            if item_type == 'function_call_output':
                output = item.get('output')
                if not isinstance(output, str):
                    output = json.dumps(output, default=str)
                append('user', {
                    'type': 'tool_result',
                    'tool_use_id': item.get('call_id'),
                    'content': output,
                })
                continue
            if role in ('user', 'assistant'):
                for block in cls._content_to_anthropic(item.get('content')):
                    append(role, block)

        return '\n\n'.join(system_parts), messages

    @classmethod
    def _content_to_anthropic(cls, content):
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
                    blocks.append({
                        'type': 'thinking',
                        'thinking': chunk['thinking'],
                        'signature': chunk.get('signature') or '',
                    })
            elif chunk.get('text'):
                blocks.append({'type': 'text', 'text': chunk['text']})
        return blocks

    @staticmethod
    def _attachment_to_anthropic(block):
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
    def _tools_to_anthropic(tools_schema):
        if not tools_schema:
            return []
        seen = set()
        out = []
        for tool in tools_schema:
            name = tool['name']
            if name in seen:
                continue
            seen.add(name)
            out.append({
                'name': name,
                'description': tool.get('description') or '',
                'input_schema': tool.get('parameters') or {
                    'type': 'object', 'properties': {},
                },
            })
        return out

    # ----------------------------------------------------------
    # Parse
    # ----------------------------------------------------------

    def _parse_response(self, payload):
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
                    assistant_content.append({
                        'type': 'output_text', 'text': text,
                    })
            elif block_type == 'thinking':
                thinking = block.get('thinking') or ''
                if thinking:
                    assistant_content.append({
                        'type': 'muk_ai_thinking',
                        'thinking': thinking,
                        'signature': block.get('signature') or '',
                    })
            elif block_type == 'tool_use':
                call_id = block.get('id')
                name = block.get('name')
                arguments = block.get('input') or {}
                tool_calls.append({
                    'call_id': call_id,
                    'name': name,
                    'arguments': arguments,
                    '_parse_error': None,
                })
                function_call_carries.append({
                    'type': 'function_call',
                    'name': name,
                    'arguments': json.dumps(arguments, default=str),
                    'call_id': call_id,
                })
        carry_inputs = []
        if assistant_content:
            carry_inputs.append({
                'role': 'assistant', 'content': assistant_content,
            })
        carry_inputs.extend(function_call_carries)
        usage = payload.get('usage') or {}
        return {
            'text': '\n'.join(text_parts).strip(),
            'tool_calls': tool_calls,
            'carry_inputs': carry_inputs,
            'usage': self._usage(
                input_tokens=usage.get('input_tokens'),
                output_tokens=usage.get('output_tokens'),
                cached_tokens=usage.get('cache_read_input_tokens'),
            ),
        }

    # ----------------------------------------------------------
    # Streaming
    # ----------------------------------------------------------

    def _stream(self, body, on_delta):
        body = {**body, 'stream': True}
        blocks_by_index = {}
        usage = self._usage()
        for event in self._post_stream('/messages', body):
            self._handle_stream_event(event, on_delta, blocks_by_index, usage)

        text_parts = []
        tool_calls = []
        function_call_carries = []
        assistant_content = []
        for index in sorted(blocks_by_index):
            entry = blocks_by_index[index]
            entry_type = entry.get('type')
            if entry_type == 'thinking':
                if entry.get('thinking'):
                    assistant_content.append({
                        'type': 'muk_ai_thinking',
                        'thinking': entry['thinking'],
                        'signature': entry.get('signature') or '',
                    })
            elif entry_type == 'text':
                text = entry.get('text') or ''
                if text:
                    text_parts.append(text)
                    assistant_content.append({
                        'type': 'output_text', 'text': text,
                    })
            elif entry_type == 'tool_use':
                args, parse_error = self._parse_tool_arguments(
                    entry.get('partial_json'),
                )
                tool_calls.append({
                    'call_id': entry['call_id'],
                    'name': entry['name'],
                    'arguments': args,
                    '_parse_error': parse_error,
                })
                function_call_carries.append({
                    'type': 'function_call',
                    'name': entry['name'],
                    'arguments': json.dumps(args, default=str),
                    'call_id': entry['call_id'],
                })
        carry_inputs = []
        if assistant_content:
            carry_inputs.append({
                'role': 'assistant', 'content': assistant_content,
            })
        carry_inputs.extend(function_call_carries)
        return {
            'text': ''.join(text_parts).strip(),
            'tool_calls': tool_calls,
            'carry_inputs': carry_inputs,
            'usage': usage,
        }

    def _handle_stream_event(self, event, on_delta, blocks_by_index, usage):
        event_type = event.get('type') or ''
        if event_type == 'message_start':
            start_usage = (event.get('message') or {}).get('usage') or {}
            usage['input_tokens'] = start_usage.get('input_tokens', 0)
            usage['cached_tokens'] = start_usage.get('cache_read_input_tokens', 0)
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
                self._call_on_delta(on_delta, 'tool_start', {
                    'call_id': entry['call_id'],
                    'name': entry['name'],
                })
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
                self._call_on_delta(on_delta, 'tool_args', {
                    'call_id': entry['call_id'],
                    'delta': partial,
                })
        elif event_type == 'message_delta':
            delta_usage = event.get('usage') or {}
            if 'output_tokens' in delta_usage:
                usage['output_tokens'] = delta_usage['output_tokens']
        elif event_type == 'error':
            error = event.get('error') or {}
            self._raise(error.get('message') or 'Unknown streaming error')
