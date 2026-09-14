from __future__ import annotations

import json
import uuid
from collections.abc import Callable

from odoo import _

from odoo.addons.muk_ai.providers.base import ProviderBase
from odoo.addons.muk_mcp.tools.schema import to_strict_schema

GROUNDING_TOOL_KEY = 'googleSearch'
CODE_EXECUTION_TOOL_KEY = 'codeExecution'

LEGACY_TOOL_MODEL_PREFIXES = ('gemini-1.', 'gemini-2.')

IMAGE_ASPECT_RATIOS = {
    f'{width}:{height}': width / height
    for width, height in (
        (1, 1),
        (2, 3),
        (3, 2),
        (3, 4),
        (4, 3),
        (4, 5),
        (5, 4),
        (9, 16),
        (16, 9),
        (21, 9),
    )
}

THINKING_LEVELS = {
    'minimal': 'low',
    'low': 'low',
    'medium': 'medium',
    'high': 'high',
    'xhigh': 'high',
    'max': 'high',
}


class GoogleProvider(ProviderBase):
    """Google Gemini generateContent adapter with grounding and streaming."""

    name = 'google'
    label = 'Google'
    default_model = 'gemini-3.8-flash'
    default_url = 'https://generativelanguage.googleapis.com/v1beta'

    supports_web_search = True
    supports_code_interpreter = True

    reasoning_error_tokens = ('thinking',)

    # ----------------------------------------------------------
    # Contract
    # ----------------------------------------------------------

    def headers(self) -> dict:
        """Return the Google API request headers with the API key."""
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
        enable_code_interpreter=False,
        extra=None,
    ) -> dict:
        """Build and run a generateContent request, streaming when requested."""
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
        thinking = {'includeThoughts': True}
        if level := THINKING_LEVELS.get((extra or {}).get('reasoning_effort')):
            thinking['thinkingLevel'] = level
        gen_cfg['thinkingConfig'] = thinking
        body['generationConfig'] = gen_cfg
        tools = self._tools_to_google(tools_schema)
        builtin = [
            {key: {}}
            for key, enabled in (
                (GROUNDING_TOOL_KEY, enable_web_search),
                (CODE_EXECUTION_TOOL_KEY, enable_code_interpreter),
            )
            if enabled
        ]
        if tools and builtin and self.serves_builtin_tools(model):
            body['toolConfig'] = {'includeServerSideToolInvocations': True}
        if tools or builtin:
            body['tools'] = tools + builtin
        return self._invoke_with_reasoning_retry(
            model,
            lambda callback: self._invoke(model, body, callback),
            on_delta,
            ((gen_cfg, ('thinkingConfig',)),),
        )

    def _invoke(self, model: str, body: dict, on_delta: Callable | None) -> dict:
        """Dispatch the request to the streaming or non-streaming path."""
        if callable(on_delta):
            path = f'/models/{model}:streamGenerateContent?alt=sse'
            return self._stream(path, body, on_delta)
        path = f'/models/{model}:generateContent'
        return self._parse_response(self._post_json(path, body))

    def serves_builtin_tools(self, model: str) -> bool:
        """Return whether the model runs built-in tools next to function calling.

        Gemini 3 serves grounding and code execution alongside the declared
        functions; earlier generations reject both the combination and the
        ``toolConfig`` opt-in.
        """
        return not model.startswith(LEGACY_TOOL_MODEL_PREFIXES)

    def generate_image(
        self,
        model: str,
        prompt: str,
        options: dict | None = None,
    ) -> dict:
        """Render one image with an image-output model through ``generateContent``.

        ``size`` maps to the closest aspect ratio; other options have none.

        :raise UserError: when the request fails or no image data comes back
        """
        config = {'responseModalities': ['IMAGE']}
        if ratio := self._aspect_ratio((options or {}).get('size')):
            config['imageConfig'] = {'aspectRatio': ratio}
        payload = self._post_json(
            f'/models/{model}:generateContent',
            {
                'contents': [{'role': 'user', 'parts': [{'text': prompt}]}],
                'generationConfig': config,
            },
            timeout=self.image_timeout,
        )
        candidate = next(iter(payload.get('candidates') or []), None) or {}
        parts = (candidate.get('content') or {}).get('parts') or []
        data = next((part['inlineData'] for part in parts if 'inlineData' in part), {})
        if not data.get('data'):
            self._raise(_('no image data returned'))
        return {
            'data_b64': data['data'],
            'mimetype': data.get('mimeType') or 'image/png',
            'revised_prompt': '',
            'usage': {'images': 1},
        }

    @staticmethod
    def _aspect_ratio(size: str | None) -> str | None:
        """Map a ``WxH`` size to the closest aspect ratio Gemini renders."""
        try:
            width, height = (int(value) for value in (size or '').lower().split('x'))
        except ValueError:
            return None
        if width <= 0 or height <= 0:
            return None
        return min(
            IMAGE_ASPECT_RATIOS,
            key=lambda ratio: abs(IMAGE_ASPECT_RATIOS[ratio] - width / height),
        )

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

    def _inputs_to_contents(self, inputs) -> tuple[str, list[dict]]:
        """Convert canonical inputs into Google system text and contents.

        Gemini rejects an unsigned ``functionCall`` part in a model turn, so a
        call this adapter did not sign replays as transcript text together with
        its result.
        """
        call_names = {}
        foreign = set()
        for item in inputs or []:
            if item.get('type') == 'function_call':
                call_id = item.get('call_id')
                name = item.get('name')
                if call_id and name:
                    call_names[call_id] = name
                if not self._carried_state(item).get('parts'):
                    foreign.add(call_id)

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
                text = self._text_from_content(item.get('content'))
                if text:
                    system_parts.append(text)
                continue
            if item_type == 'function_call':
                if parts := self._carried_state(item).get('parts'):
                    for part in parts:
                        append('model', part)
                else:
                    append('model', {'text': self._transcript_call(item)})
                continue
            if item_type == 'function_call_output':
                call_id = item.get('call_id')
                name = call_names.get(call_id) or ''
                output = item.get('output')
                if call_id in foreign:
                    append('user', {'text': self._transcript_result(name, output)})
                    continue
                if isinstance(output, str):
                    try:
                        parsed = json.loads(output)
                        response = (
                            parsed if isinstance(parsed, dict) else {'output': parsed}
                        )
                    except ValueError:
                        response = {'output': output}
                elif isinstance(output, dict):
                    response = output
                else:
                    response = {'output': output}
                append(
                    'user',
                    {
                        'functionResponse': {
                            'name': name,
                            'response': response,
                        },
                    },
                )
                continue
            if role == 'assistant':
                for part in self._content_to_google(item.get('content')):
                    append('model', part)
            elif role == 'user':
                for part in self._content_to_google(item.get('content')):
                    append('user', part)

        return '\n\n'.join(system_parts), contents

    @staticmethod
    def _transcript_call(item: dict) -> str:
        """Render a function call this adapter never signed as model text."""
        return f'[tool call] {item.get("name") or ""}({item.get("arguments") or "{}"})'

    @staticmethod
    def _transcript_result(name: str, output) -> str:
        """Render the result of an unsigned function call as user text."""
        if not isinstance(output, str):
            output = json.dumps(output, default=str)
        return f'[tool result] {name}: {output}'

    @classmethod
    def _content_to_google(cls, content) -> list[dict]:
        """Convert canonical content blocks into Google content parts."""
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
    def _attachment_to_google(block: dict) -> dict:
        """Convert an attachment block into a Google inline-data or text part."""
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
    def _tools_to_google(tools_schema) -> list[dict]:
        """Convert tool schemas into Google function declarations, deduplicated by name."""
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
                'type': 'object',
                'properties': {},
            }
            decls.append(
                {
                    'name': name,
                    'description': tool.get('description') or '',
                    'parameters': to_strict_schema(params),
                }
            )
        if not decls:
            return []
        return [{'functionDeclarations': decls}]

    # ----------------------------------------------------------
    # Parse
    # ----------------------------------------------------------

    @classmethod
    def _usage_from_google(cls, meta: dict) -> dict:
        """Normalize a ``usageMetadata`` block, folding reasoning into the output.

        ``candidatesTokenCount`` excludes ``thoughtsTokenCount``; both bill at
        the output rate, so they are summed here.
        """
        return cls._usage(
            input_tokens=meta.get('promptTokenCount'),
            output_tokens=(meta.get('candidatesTokenCount') or 0)
            + (meta.get('thoughtsTokenCount') or 0),
            cache_read_tokens=meta.get('cachedContentTokenCount'),
        )

    def _parse_response(self, payload: dict) -> dict:
        """Parse a non-streaming response into text, tool calls, carry inputs, and usage."""
        turn = self._new_turn()
        candidates = payload.get('candidates') or []
        if candidates:
            for part in (candidates[0].get('content') or {}).get('parts') or []:
                self._consume_part(part, turn)
        return self._turn_result(
            turn,
            self._usage_from_google(payload.get('usageMetadata') or {}),
            truncated=bool(candidates)
            and candidates[0].get('finishReason') == 'MAX_TOKENS',
        )

    @staticmethod
    def _new_turn() -> dict:
        """Return the accumulators collecting one model turn."""
        return {
            'text': [],
            'message': [],
            'tool_calls': [],
            'carry': [],
            'builtin': [],
            'replay': None,
        }

    def _turn_result(
        self,
        turn: dict,
        usage: dict,
        on_delta: Callable | None = None,
        truncated: bool = False,
    ) -> dict:
        """Assemble the provider result from a finished model turn.

        Built-in parts still pending when the turn ends close the sequence of
        the last function call, so the next round replays that call bracketed
        by the signed parts exactly as the wire produced them.
        """
        if turn['builtin'] and turn['replay'] is not None:
            turn['replay'].extend(turn['builtin'])
            turn['builtin'] = []
        if turn['message']:
            turn['carry'].insert(
                0, self._assistant_text_carry(''.join(turn['message']))
            )
        result = {
            'text': ''.join(turn['text']).strip(),
            'tool_calls': turn['tool_calls'],
            'carry_inputs': turn['carry'],
            'usage': usage,
        }
        if truncated:
            self._apply_truncation(result, on_delta, self.max_tokens)
        return result

    def _consume_part(self, part: dict, turn: dict, on_delta=None) -> None:
        """Consume one response part into the turn, forwarding streaming deltas.

        Thoughts stream as reasoning and stay out of the answer. A ``toolCall``
        or ``toolResponse`` part is kept verbatim for the function call it
        brackets, which cannot be replayed without it.
        """
        if part.get('thought'):
            if text := part.get('text') or '':
                self._call_on_delta(on_delta, 'reasoning', {'delta': text})
            return
        if 'text' in part:
            if not (text := part.get('text') or ''):
                return
            turn['text'].append(text)
            turn['message'].append(text)
            self._call_on_delta(on_delta, 'text', {'delta': text})
            return
        if 'functionCall' in part:
            call, carry = self._function_call_entries(part, turn)
            self._call_on_delta(
                on_delta,
                'tool_start',
                {
                    'call_id': call['call_id'],
                    'name': call['name'],
                },
            )
            self._call_on_delta(
                on_delta,
                'tool_args',
                {
                    'call_id': call['call_id'],
                    'delta': carry['arguments'],
                },
            )
            turn['tool_calls'].append(call)
            turn['carry'].append(carry)
            return
        if snippet := self._code_snippet(part):
            turn['text'].append(snippet)
            turn['message'].append(snippet)
            self._call_on_delta(on_delta, 'text', {'delta': snippet})
            return
        turn['builtin'].append(part)

    @staticmethod
    def _code_snippet(part: dict) -> str:
        """Render a code execution part as Markdown, empty when it is not one."""
        if 'executableCode' in part:
            code = part['executableCode'] or {}
            language = (code.get('language') or '').lower()
            return f'\n\n```{language}\n{code.get("code") or ""}\n```\n\n'
        if 'codeExecutionResult' in part:
            result = part['codeExecutionResult'] or {}
            return f'\n\n```\n{result.get("output") or ""}\n```\n\n'
        return ''

    def _function_call_entries(self, part: dict, turn: dict) -> tuple[dict, dict]:
        """Build the tool call and the carry item for one ``functionCall`` part.

        Gemini rejects a replayed call whose ``thoughtSignature`` and bracketing
        built-in parts are not echoed back verbatim, so those parts are carried
        as this provider's private state.
        """
        fc = part['functionCall']
        name = fc.get('name') or ''
        args = fc.get('args') or {}
        call_id = self._make_call_id()
        call = {
            'call_id': call_id,
            'name': name,
            'arguments': args,
            '_parse_error': None,
        }
        turn['replay'] = [*turn['builtin'], part]
        turn['builtin'] = []
        carry = self._carry_state(
            {
                'type': 'function_call',
                'name': name,
                'arguments': json.dumps(args, default=str),
                'call_id': call_id,
            },
            {'parts': turn['replay']},
        )
        return call, carry

    @staticmethod
    def _assistant_text_carry(text: str) -> dict:
        """Build an assistant carry-input message from accumulated text."""
        return {
            'role': 'assistant',
            'content': [{'type': 'output_text', 'text': text}],
        }

    @staticmethod
    def _make_call_id() -> str:
        """Generate a synthetic call id for a Google function call."""
        return f'call_google_{uuid.uuid4().hex[:16]}'

    # ----------------------------------------------------------
    # Streaming
    # ----------------------------------------------------------

    def _stream(self, path: str, body: dict, on_delta) -> dict:
        """Stream a generateContent request and assemble the final result."""
        turn = self._new_turn()
        raw_usage = {}
        meta = {}
        for event in self._post_stream(path, body):
            self._handle_stream_event(event, turn, on_delta, raw_usage, meta)
        return self._turn_result(
            turn,
            self._usage_from_google(raw_usage),
            on_delta=on_delta,
            truncated=bool(meta.get('truncated')),
        )

    def _handle_stream_event(
        self,
        event: dict,
        turn: dict,
        on_delta,
        raw_usage: dict,
        meta: dict,
    ) -> None:
        """Apply one streaming event to the turn and forward deltas.

        :param raw_usage: accumulates raw ``usageMetadata`` fields, normalized
            once by :meth:`_usage_from_google` after the stream ends
        :raise UserError: when the event signals an error or safety block.
        """
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
            if finish == 'MAX_TOKENS':
                meta['truncated'] = True
            elif finish and finish not in ('STOP', 'FINISH_REASON_UNSPECIFIED'):
                self._raise(f'Response blocked by Google (finishReason: {finish})')
            for part in (first.get('content') or {}).get('parts') or []:
                self._consume_part(part, turn, on_delta)
        raw_usage.update(event.get('usageMetadata') or {})
