import json
import uuid

from odoo.addons.muk_mcp.tools.schema import to_strict_schema

from .base import ProviderBase

GROUNDING_TOOL_KEY = 'googleSearch'
CODE_EXECUTION_TOOL_KEY = 'codeExecution'
IMAGE_OUTPUT_MODEL = 'gemini-2.5-flash-image'


class GoogleProvider(ProviderBase):

    name = 'google'
    label = "Google"
    default_model = 'gemini-2.5-flash'
    default_url = 'https://generativelanguage.googleapis.com/v1beta'

    supports_web_search = True
    supports_image_generation = True
    supports_code_interpreter = True

    # ----------------------------------------------------------
    # Contract
    # ----------------------------------------------------------

    def headers(self):
        return {
            'x-goog-api-key': self.api_key,
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
        if enable_image_generation:
            model = IMAGE_OUTPUT_MODEL
        else:
            model = self.model_for(model)
        system_text, contents = self._inputs_to_contents(inputs)
        body = {'contents': contents}
        if system_text:
            body['systemInstruction'] = {'parts': [{'text': system_text}]}
        gen_cfg = {}
        if self.max_tokens:
            gen_cfg['maxOutputTokens'] = self.max_tokens
        if text_schema:
            gen_cfg['responseMimeType'] = 'application/json'
            gen_cfg['responseSchema'] = text_schema['schema']
        if gen_cfg:
            body['generationConfig'] = gen_cfg
        tools = self._tools_to_google(tools_schema)
        if enable_web_search:
            tools.append({GROUNDING_TOOL_KEY: {}})
        if enable_code_interpreter:
            tools.append({CODE_EXECUTION_TOOL_KEY: {}})
        if tools:
            body['tools'] = tools
        if callable(on_delta):
            path = f'/models/{model}:streamGenerateContent?alt=sse'
            return self._stream(path, body, on_delta)
        path = f'/models/{model}:generateContent'
        return self._parse_response(self._post_json(path, body))

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
    def _inputs_to_contents(cls, inputs):
        call_names = {}
        for item in inputs or []:
            if item.get('type') == 'function_call':
                call_id = item.get('call_id')
                name = item.get('name')
                if call_id and name:
                    call_names[call_id] = name

        system_parts = []
        contents = []

        def append(role, part):
            if contents and contents[-1]['role'] == role:
                contents[-1]['parts'].append(part)
            else:
                contents.append({'role': role, 'parts': [part]})

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
                    args = json.loads(item.get('arguments') or '{}')
                except ValueError:
                    args = {}
                append('model', {
                    'functionCall': {
                        'name': item.get('name') or '',
                        'args': args,
                    },
                })
                continue
            if item_type == 'function_call_output':
                call_id = item.get('call_id')
                name = call_names.get(call_id) or ''
                output = item.get('output')
                if isinstance(output, str):
                    try:
                        parsed = json.loads(output)
                        response = parsed if isinstance(parsed, dict) else {'output': parsed}
                    except ValueError:
                        response = {'output': output}
                elif isinstance(output, dict):
                    response = output
                else:
                    response = {'output': output}
                append('user', {
                    'functionResponse': {
                        'name': name,
                        'response': response,
                    },
                })
                continue
            if role == 'assistant':
                for part in cls._content_to_google(item.get('content')):
                    append('model', part)
            elif role == 'user':
                for part in cls._content_to_google(item.get('content')):
                    append('user', part)

        return '\n\n'.join(system_parts), contents

    @classmethod
    def _content_to_google(cls, content):
        if isinstance(content, str):
            return [{'text': content}]
        parts = []
        for chunk in content or []:
            if not isinstance(chunk, dict):
                continue
            chunk_type = chunk.get('type')
            if chunk_type == 'muk_ai_attachment':
                parts.append(cls._attachment_to_google(chunk))
            elif chunk.get('text'):
                parts.append({'text': chunk['text']})
        return parts

    @staticmethod
    def _attachment_to_google(block):
        strategy = block.get('strategy')
        mimetype = block.get('mimetype') or 'application/octet-stream'
        data_b64 = block.get('data_b64') or ''
        filename = block.get('filename') or 'attachment'
        if strategy == 'image':
            return {
                'inlineData': {
                    'mimeType': mimetype,
                    'data': data_b64,
                },
            }
        if strategy == 'file' and mimetype == 'application/pdf':
            return {
                'inlineData': {
                    'mimeType': 'application/pdf',
                    'data': data_b64,
                },
            }
        text = block.get('inline_text') or ''
        prefix = f'--- File: {filename} ({mimetype}) ---\n'
        if block.get('truncated'):
            text += '\n[truncated]'
        return {'text': prefix + text}

    @staticmethod
    def _tools_to_google(tools_schema):
        if not tools_schema:
            return []
        decls = []
        seen = set()
        for tool in tools_schema:
            name = tool['name']
            if name in seen:
                continue
            seen.add(name)
            params = tool.get('parameters') or {
                'type': 'object', 'properties': {},
            }
            decls.append({
                'name': name,
                'description': tool.get('description') or '',
                'parameters': to_strict_schema(params),
            })
        if not decls:
            return []
        return [{'functionDeclarations': decls}]

    # ----------------------------------------------------------
    # Parse
    # ----------------------------------------------------------

    def _parse_response(self, payload):
        candidates = payload.get('candidates') or []
        text_parts = []
        tool_calls = []
        carry_inputs = []
        message_text_parts = []
        if candidates:
            content = candidates[0].get('content') or {}
            for part in content.get('parts') or []:
                self._consume_part(
                    part, text_parts, message_text_parts, tool_calls, carry_inputs,
                )
        if message_text_parts:
            carry_inputs.insert(0, self._assistant_text_carry(''.join(message_text_parts)))
        usage = payload.get('usageMetadata') or {}
        return {
            'text': '\n'.join(text_parts).strip(),
            'tool_calls': tool_calls,
            'carry_inputs': carry_inputs,
            'usage': self._usage(
                input_tokens=usage.get('promptTokenCount'),
                output_tokens=usage.get('candidatesTokenCount'),
                cached_tokens=usage.get('cachedContentTokenCount'),
            ),
        }

    @classmethod
    def _consume_part(cls, part, text_parts, message_text_parts, tool_calls, carry_inputs):
        if 'functionCall' in part:
            fc = part['functionCall']
            name = fc.get('name') or ''
            args = fc.get('args') or {}
            call_id = cls._make_call_id()
            tool_calls.append({
                'call_id': call_id,
                'name': name,
                'arguments': args,
                '_parse_error': None,
            })
            carry_inputs.append({
                'type': 'function_call',
                'name': name,
                'arguments': json.dumps(args, default=str),
                'call_id': call_id,
            })
            return
        if 'text' in part:
            text = part.get('text') or ''
            if text:
                text_parts.append(text)
                message_text_parts.append(text)
            return
        if 'inlineData' in part:
            data = part['inlineData']
            mime = data.get('mimeType') or 'image/png'
            b64 = data.get('data') or ''
            snippet = f'![image](data:{mime};base64,{b64})'
            text_parts.append(snippet)
            message_text_parts.append(snippet)
            return
        if 'executableCode' in part:
            code = part['executableCode']
            lang = (code.get('language') or '').lower()
            snippet = f"```{lang}\n{code.get('code') or ''}\n```"
            text_parts.append(snippet)
            message_text_parts.append(snippet)
            return
        if 'codeExecutionResult' in part:
            result = part['codeExecutionResult']
            snippet = f"```\n{result.get('output') or ''}\n```"
            text_parts.append(snippet)
            message_text_parts.append(snippet)

    @staticmethod
    def _assistant_text_carry(text):
        return {
            'role': 'assistant',
            'content': [{'type': 'output_text', 'text': text}],
        }

    @staticmethod
    def _make_call_id():
        return f'call_google_{uuid.uuid4().hex[:16]}'

    # ----------------------------------------------------------
    # Streaming
    # ----------------------------------------------------------

    def _stream(self, path, body, on_delta):
        text_parts = []
        message_text_parts = []
        tool_calls = []
        carry_inputs = []
        usage = self._usage()
        for event in self._post_stream(path, body):
            self._handle_stream_event(
                event,
                on_delta,
                text_parts,
                message_text_parts,
                tool_calls,
                carry_inputs,
                usage,
            )
        if message_text_parts:
            carry_inputs.insert(0, self._assistant_text_carry(''.join(message_text_parts)))
        return {
            'text': ''.join(text_parts).strip(),
            'tool_calls': tool_calls,
            'carry_inputs': carry_inputs,
            'usage': usage,
        }

    def _handle_stream_event(
        self,
        event,
        on_delta,
        text_parts,
        message_text_parts,
        tool_calls,
        carry_inputs,
        usage,
    ):
        if error := event.get('error'):
            message = error.get('message') or 'Unknown streaming error'
            if code := error.get('status') or error.get('code'):
                message = f'{message} (code: {code})'
            self._raise(message)
        if block := (event.get('promptFeedback') or {}).get('blockReason'):
            self._raise(f'Prompt blocked by safety filter (reason: {block})')
        candidates = event.get('candidates') or []
        if candidates:
            first = candidates[0]
            finish = first.get('finishReason')
            if finish and finish not in ('STOP', 'MAX_TOKENS', 'FINISH_REASON_UNSPECIFIED'):
                self._raise(f'Response blocked by Google (finishReason: {finish})')
            content = first.get('content') or {}
            for part in content.get('parts') or []:
                self._stream_part(
                    part, on_delta, text_parts, message_text_parts,
                    tool_calls, carry_inputs,
                )
        meta = event.get('usageMetadata') or {}
        if meta:
            if 'promptTokenCount' in meta:
                usage['input_tokens'] = meta['promptTokenCount']
            if 'candidatesTokenCount' in meta:
                usage['output_tokens'] = meta['candidatesTokenCount']
            if 'cachedContentTokenCount' in meta:
                usage['cached_tokens'] = meta['cachedContentTokenCount']

    def _stream_part(self, part, on_delta, text_parts, message_text_parts, tool_calls, carry_inputs):
        if 'text' in part:
            text = part.get('text') or ''
            if not text:
                return
            text_parts.append(text)
            message_text_parts.append(text)
            self._call_on_delta(on_delta, 'text', {'delta': text})
            return
        if 'functionCall' in part:
            fc = part['functionCall']
            name = fc.get('name') or ''
            args = fc.get('args') or {}
            call_id = self._make_call_id()
            args_json = json.dumps(args, default=str)
            self._call_on_delta(on_delta, 'tool_start', {
                'call_id': call_id,
                'name': name,
            })
            self._call_on_delta(on_delta, 'tool_args', {
                'call_id': call_id,
                'delta': args_json,
            })
            tool_calls.append({
                'call_id': call_id,
                'name': name,
                'arguments': args,
                '_parse_error': None,
            })
            carry_inputs.append({
                'type': 'function_call',
                'name': name,
                'arguments': args_json,
                'call_id': call_id,
            })
            return
        if 'inlineData' in part:
            data = part['inlineData']
            mime = data.get('mimeType') or 'image/png'
            b64 = data.get('data') or ''
            snippet = f'![image](data:{mime};base64,{b64})'
            text_parts.append(snippet)
            message_text_parts.append(snippet)
            self._call_on_delta(on_delta, 'text', {'delta': snippet})
            return
        if 'executableCode' in part:
            code = part['executableCode']
            lang = (code.get('language') or '').lower()
            snippet = f"```{lang}\n{code.get('code') or ''}\n```"
            text_parts.append(snippet)
            message_text_parts.append(snippet)
            self._call_on_delta(on_delta, 'text', {'delta': snippet})
            return
        if 'codeExecutionResult' in part:
            result = part['codeExecutionResult']
            snippet = f"```\n{result.get('output') or ''}\n```"
            text_parts.append(snippet)
            message_text_parts.append(snippet)
            self._call_on_delta(on_delta, 'text', {'delta': snippet})
