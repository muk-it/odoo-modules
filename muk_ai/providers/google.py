from __future__ import annotations

import contextlib
import functools
import json
import uuid
from collections.abc import Callable

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
    # Functions
    # ----------------------------------------------------------

    def headers(self) -> dict:
        """Return the Google API request headers with the API key."""
        return {
            'x-goog-api-key': self.api_key,
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
        """Build and stream a generateContent request."""
        model = self.model_for(model)
        system_text, contents = self._inputs_to_contents(inputs)
        config = {'thinkingConfig': {'includeThoughts': True}}
        body = {'contents': contents, 'generationConfig': config}
        if system_text:
            body['systemInstruction'] = {'parts': [{'text': system_text}]}
        if max_tokens := self.provider.max_tokens:
            config['maxOutputTokens'] = max_tokens
        if text_schema:
            config['responseMimeType'] = 'application/json'
            config['responseSchema'] = text_schema['schema']
        if level := THINKING_LEVELS.get(reasoning_effort):
            config['thinkingConfig']['thinkingLevel'] = level
        declarations = [
            {
                'name': name,
                'description': description,
                'parameters': to_strict_schema(parameters),
            }
            for name, description, parameters in self._unique_tools(tools_schema)
        ]
        tools = [{'functionDeclarations': declarations}] if declarations else []
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
        path = f'/models/{model}:streamGenerateContent?alt=sse'
        return self._invoke_with_reasoning_retry(
            model,
            lambda callback: self._stream(path, body, callback),
            on_delta,
            ((config, ('thinkingConfig',)),),
        )

    def serves_builtin_tools(self, model: str) -> bool:
        """Return whether the model runs built-in tools next to function calling.

        Gemini 3 serves grounding and code execution alongside the declared
        functions; earlier generations reject the combination and the opt-in.
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
            timeout=self.provider.image_timeout,
        )
        candidate = next(iter(payload.get('candidates') or []), None) or {}
        parts = (candidate.get('content') or {}).get('parts') or []
        data = next((part['inlineData'] for part in parts if 'inlineData' in part), {})
        if not data.get('data'):
            self._raise(self.env._('no image data returned'))
        return {
            'data_b64': data['data'],
            'mimetype': data.get('mimeType') or 'image/png',
            'revised_prompt': '',
            'usage': {'images': 1},
        }

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

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

    def _inputs_to_contents(self, inputs) -> tuple[str, list[dict]]:
        """Convert canonical inputs into Google system text and contents.

        Gemini rejects an unsigned ``functionCall`` part in a model turn, so a
        call this adapter did not sign replays as transcript text together with
        its result.
        """
        names = {}
        foreign = set()
        for item in inputs or []:
            if item.get('type') == 'function_call':
                names[item.get('call_id')] = item.get('name') or ''
                if not self._carried_state(item).get('parts'):
                    foreign.add(item.get('call_id'))
        contents = []
        append = functools.partial(self._append_turn, contents, 'parts')
        for item in inputs or []:
            role = item.get('role')
            if item.get('type') == 'function_call':
                if parts := self._carried_state(item).get('parts'):
                    for part in parts:
                        append('model', part)
                else:
                    call = f'{item.get("name") or ""}({item.get("arguments") or "{}"})'
                    append('model', {'text': f'[tool call] {call}'})
            elif item.get('type') == 'function_call_output':
                name = names.get(item.get('call_id')) or ''
                output = item.get('output')
                if item.get('call_id') in foreign:
                    if not isinstance(output, str):
                        output = json.dumps(output, default=str)
                    append('user', {'text': f'[tool result] {name}: {output}'})
                    continue
                if isinstance(output, str):
                    with contextlib.suppress(ValueError):
                        output = json.loads(output)
                response = output if isinstance(output, dict) else {'output': output}
                append(
                    'user', {'functionResponse': {'name': name, 'response': response}}
                )
            elif role in ('user', 'assistant'):
                for part in self._content_parts(item.get('content')):
                    append('model' if role == 'assistant' else 'user', part)
        return self._system_text(inputs), contents

    @staticmethod
    def _text_part(text: str) -> dict:
        """Return the Google part carrying a text."""
        return {'text': text}

    @classmethod
    def _attachment_part(cls, block: dict) -> dict:
        """Convert an attachment block into a Google inline-data or text part."""
        mimetype = block.get('mimetype') or 'application/octet-stream'
        strategy = block.get('strategy')
        if strategy == 'image' or (
            strategy == 'file' and mimetype == 'application/pdf'
        ):
            return {
                'inlineData': {
                    'mimeType': mimetype,
                    'data': block.get('data_b64') or '',
                }
            }
        return {'text': cls._attachment_text(block)}

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

    def _stream(self, path: str, body: dict, on_delta: Callable | None) -> dict:
        """Stream a generateContent request and assemble the final result.

        Built-in parts still pending when the turn ends close the sequence of
        the last function call, so the next round replays that call bracketed
        by the signed parts exactly as the wire produced them.
        """
        turn = {
            'text': [],
            'tool_calls': [],
            'carry': [],
            'builtin': [],
            'replay': None,
        }
        usage, meta = {}, {}
        for event in self._post_stream(path, body):
            self._handle_stream_event(event, turn, on_delta, usage, meta)
        if turn['builtin'] and turn['replay'] is not None:
            turn['replay'].extend(turn['builtin'])
        text = ''.join(turn['text'])
        carry = [self._text_carry(text)] if text else []
        return self._result(
            text,
            turn['tool_calls'],
            [*carry, *turn['carry']],
            self._usage_from_google(usage),
            on_delta,
            bool(meta.get('truncated')),
            self.provider.max_tokens,
        )

    def _handle_stream_event(
        self,
        event: dict,
        turn: dict,
        on_delta: Callable | None,
        usage: dict,
        meta: dict,
    ) -> None:
        """Apply one streaming event to the turn and forward deltas.

        :param usage: collects the raw ``usageMetadata`` fields of the stream
        :raise UserError: when the event signals an error or safety block.
        """
        if error := event.get('error'):
            self._raise_stream_error(error, 'status', 'code')
        if block := (event.get('promptFeedback') or {}).get('blockReason'):
            self._raise(f'Prompt blocked by safety filter (reason: {block})')
        if candidates := event.get('candidates') or []:
            finish = candidates[0].get('finishReason')
            if finish == 'MAX_TOKENS':
                meta['truncated'] = True
            elif finish and finish not in ('STOP', 'FINISH_REASON_UNSPECIFIED'):
                self._raise(f'Response blocked by Google (finishReason: {finish})')
            for part in (candidates[0].get('content') or {}).get('parts') or []:
                self._consume_part(part, turn, on_delta)
        usage.update(event.get('usageMetadata') or {})

    def _consume_part(self, part: dict, turn: dict, on_delta: Callable | None) -> None:
        """Consume one response part into the turn, forwarding streaming deltas.

        Thoughts stream as reasoning and stay out of the answer. A ``toolCall``
        or ``toolResponse`` part is kept verbatim for the function call it
        brackets, which cannot be replayed without it.
        """
        if part.get('thought'):
            if text := part.get('text'):
                self._call_on_delta(on_delta, 'reasoning', {'delta': text})
        elif 'functionCall' in part:
            call = self._tool_call(
                f'call_google_{uuid.uuid4().hex[:16]}',
                part['functionCall'].get('name') or '',
                part['functionCall'].get('args') or {},
            )
            turn['replay'] = [*turn['builtin'], part]
            turn['builtin'] = []
            item = self._call_item(call)
            self._call_on_delta(
                on_delta,
                'tool_start',
                {'call_id': call['call_id'], 'name': call['name']},
            )
            self._call_on_delta(
                on_delta,
                'tool_args',
                {'call_id': call['call_id'], 'delta': item['arguments']},
            )
            turn['tool_calls'].append(call)
            turn['carry'].append(self._carry_state(item, {'parts': turn['replay']}))
        elif text := part.get('text') or self._code_snippet(part):
            turn['text'].append(text)
            self._call_on_delta(on_delta, 'text', {'delta': text})
        elif 'text' not in part:
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
