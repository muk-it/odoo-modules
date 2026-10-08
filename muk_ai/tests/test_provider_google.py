from __future__ import annotations

from odoo.exceptions import UserError

from odoo.addons.muk_ai.tests.common import json_response
from odoo.addons.muk_ai.tests.providers import (
    CASES,
    TOOLS,
    USER,
    ProviderTestCase,
    gemini,
)

ASKED = {'role': 'user', 'parts': [{'text': 'hi'}]}


class TestGoogleProvider(ProviderTestCase):
    """Verify the Gemini-only parts of the wire: signatures, built-ins and images."""

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _call(self, name: str, signature: str = '') -> dict:
        """Build a ``functionCall`` part, signed when Gemini signs it."""
        part = {'functionCall': {'name': name, 'args': {'model': 'res.partner'}}}
        return {**part, 'thoughtSignature': signature} if signature else part

    def _builtin(self, key: str) -> dict:
        """Build a signed ``toolCall`` or ``toolResponse`` part of a built-in tool."""
        return {key: {'name': 'google_search'}, 'thoughtSignature': f'sig-{key}'}

    def _carried(self, name: str, call_id: str, signature: str = '') -> dict:
        """Build the stored function-call item of a round, signed or not."""
        item = {
            'type': 'function_call',
            'name': name,
            'arguments': '{"model": "res.partner"}',
            'call_id': call_id,
        }
        if signature:
            item['provider_state'] = {
                'google': {'parts': [self._call(name, signature)]}
            }
        return item

    def _output(self, call_id: str, output: str = '{"count": 3}') -> dict:
        """Build the tool result answering a stored call."""
        return {'type': 'function_call_output', 'call_id': call_id, 'output': output}

    def _image(self, size: str | None = None, mimetype: str = '') -> tuple[dict, dict]:
        """Render one image and return the body sent and the result."""
        part = {
            'inlineData': {
                'data': 'AAA=',
                **({'mimeType': mimetype} if mimetype else {}),
            }
        }
        with self._wire(
            json_response({'candidates': [{'content': {'parts': [part]}}]})
        ) as sent:
            result = (
                self.providers['google']
                ._get_client()
                .generate_image('gemini-3.1-flash-image', 'a dot', {'size': size})
            )
        return sent[0], result

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_each_function_call_carries_its_own_signature(self):
        for label, parts in (
            ('signed', [self._call('search_read', 'sig-a')]),
            ('unsigned', [self._call('search_read')]),
            (
                'parallel',
                [
                    self._call('search_read', 'sig-a'),
                    self._call('read_group', 'sig-b'),
                    self._call('search_count'),
                ],
            ),
        ):
            with self.subTest(calls=label):
                result, _deltas, _sent = self._stream('google', [gemini(*parts)])
                carry = result['carry_inputs']
                self.assertEqual(
                    [item['provider_state']['google']['parts'] for item in carry],
                    [[part] for part in parts],
                )
                self.assertEqual(
                    [item['call_id'] for item in carry],
                    [call['call_id'] for call in result['tool_calls']],
                )

    def test_a_turn_keeps_built_in_parts_with_the_call_they_bracket(self):
        bracket = ['toolCall', 'functionCall', 'toolResponse']
        call, opened, closed = (
            self._call('search_read'),
            self._builtin('toolCall'),
            self._builtin('toolResponse'),
        )
        for label, chunks, text, carried in (
            (
                'one chunk',
                [gemini(opened, call, closed)],
                '',
                [('function_call', bracket)],
            ),
            (
                'two chunks',
                [gemini(opened, call), gemini(closed)],
                '',
                [('function_call', bracket)],
            ),
            (
                'no call',
                [gemini(opened, {'text': 'the answer'}, closed)],
                'the answer',
                [('assistant', [])],
            ),
            (
                'code execution',
                [
                    gemini(
                        {'executableCode': {'language': 'PYTHON', 'code': 'print(1)'}},
                        {'codeExecutionResult': {'output': '1'}},
                    )
                ],
                '```python\nprint(1)\n```\n\n\n\n```\n1\n```',
                [('assistant', [])],
            ),
        ):
            with self.subTest(turn=label):
                result, _deltas, _sent = self._stream('google', chunks)
                self.assertEqual(result['text'], text)
                self.assertEqual(
                    [
                        (
                            item.get('type') or item['role'],
                            [
                                next(iter(part))
                                for part in item.get('provider_state', {})
                                .get('google', {})
                                .get('parts', [])
                            ],
                        )
                        for item in result['carry_inputs']
                    ],
                    carried,
                )

    def test_stored_calls_replay_signed_or_as_transcript_text(self):
        response = {'name': 'search_read', 'response': {'count': 3}}
        for label, inputs, contents in (
            (
                'signed',
                [self._carried('search_read', 'c1', 'sig-a'), self._output('c1')],
                [
                    {'role': 'model', 'parts': [self._call('search_read', 'sig-a')]},
                    {'role': 'user', 'parts': [{'functionResponse': response}]},
                ],
            ),
            (
                'parallel',
                [
                    self._carried('search_read', 'c1', 'sig-a'),
                    self._carried('read_group', 'c2', 'sig-b'),
                    self._output('c2', '[1, 2]'),
                ],
                [
                    {
                        'role': 'model',
                        'parts': [
                            self._call('search_read', 'sig-a'),
                            self._call('read_group', 'sig-b'),
                        ],
                    },
                    {
                        'role': 'user',
                        'parts': [
                            {
                                'functionResponse': {
                                    'name': 'read_group',
                                    'response': {'output': [1, 2]},
                                }
                            }
                        ],
                    },
                ],
            ),
            (
                'unsigned',
                [self._carried('search_read', 'c1'), self._output('c1')],
                [
                    {
                        'role': 'model',
                        'parts': [
                            {
                                'text': '[tool call] search_read({"model": "res.partner"})'
                            }
                        ],
                    },
                    {
                        'role': 'user',
                        'parts': [{'text': '[tool result] search_read: {"count": 3}'}],
                    },
                ],
            ),
        ):
            with self.subTest(call=label):
                _result, _deltas, sent = self._stream(
                    'google', CASES['google'].text, inputs=[USER, *inputs]
                )
                self.assertEqual(sent[0]['json']['contents'], [ASKED, *contents])

    def test_a_streamed_call_replays_its_parts_verbatim(self):
        parts = [
            self._builtin('toolCall'),
            self._call('search_read', 'sig-a'),
            self._builtin('toolResponse'),
        ]
        first, _deltas, _sent = self._stream(
            'google', [gemini(*parts[:2]), gemini(parts[2])]
        )
        call_id = first['tool_calls'][0]['call_id']
        _result, _deltas, sent = self._stream(
            'google',
            CASES['google'].text,
            inputs=[USER, *first['carry_inputs'], self._output(call_id)],
        )
        self.assertEqual(
            sent[0]['json']['contents'][1], {'role': 'model', 'parts': parts}
        )

    def test_server_side_invocations_are_opted_into_beside_functions_only(self):
        for tools, web, code, model, opted in (
            (TOOLS, True, False, 'gemini-3.8-flash', True),
            (TOOLS, False, True, 'gemini-3.8-flash', True),
            (None, True, True, 'gemini-3.8-flash', False),
            (TOOLS, False, False, 'gemini-3.8-flash', False),
            (TOOLS, True, False, 'gemini-2.5-flash', False),
        ):
            with self.subTest(tools=bool(tools), web=web, code=code, model=model):
                _result, _deltas, sent = self._stream(
                    'google',
                    CASES['google'].text,
                    model=model,
                    tools_schema=tools,
                    enable_web_search=web,
                    enable_code_interpreter=code,
                )
                self.assertEqual(
                    sent[0]['json'].get('toolConfig'),
                    {'includeServerSideToolInvocations': True} if opted else None,
                )

    def test_a_blocked_or_failed_stream_raises_a_user_error(self):
        for chunk, message in (
            ({'promptFeedback': {'blockReason': 'SAFETY'}}, 'Prompt blocked .* SAFETY'),
            (gemini({'text': 'x'}, finish='RECITATION'), 'finishReason: RECITATION'),
            (CASES['google'].error('Overloaded'), r'Overloaded \(code: INTERNAL\)'),
        ):
            with (
                self.subTest(failure=message),
                self._wire([chunk]),
                self.assertRaisesRegex(UserError, message),
            ):
                self.providers['google']._request_responses(
                    inputs=[USER], on_delta=lambda kind, data: None
                )

    def test_an_image_size_becomes_the_closest_aspect_ratio(self):
        for size, ratio in (
            ('1536x1024', '3:2'),
            ('1024x1024', '1:1'),
            ('1024x1536', '2:3'),
            ('1920X1080', '16:9'),
            ('1000x900', '1:1'),
            ('large', None),
            ('0x10', None),
            (None, None),
        ):
            with self.subTest(size=size):
                sent, _result = self._image(size)
                self.assertEqual(
                    sent['json'],
                    {
                        'contents': [{'role': 'user', 'parts': [{'text': 'a dot'}]}],
                        'generationConfig': {
                            'responseModalities': ['IMAGE'],
                            **(
                                {'imageConfig': {'aspectRatio': ratio}} if ratio else {}
                            ),
                        },
                    },
                )

    def test_image_generation_answers_the_inline_image(self):
        self.providers['google'].write({'request_timeout': 45, 'image_timeout': 300})
        for mimetype, answered in (('image/jpeg', 'image/jpeg'), ('', 'image/png')):
            with self.subTest(mimetype=mimetype):
                sent, result = self._image(mimetype=mimetype)
                self.assertTrue(
                    sent['url'].endswith(
                        '/models/gemini-3.1-flash-image:generateContent'
                    )
                )
                self.assertEqual(sent['timeout'], 300)
                self.assertEqual(
                    result,
                    {
                        'data_b64': 'AAA=',
                        'mimetype': answered,
                        'revised_prompt': '',
                        'usage': {'images': 1},
                    },
                )
        with (
            self._wire(json_response(CASES['google'].reply)),
            self.assertRaisesRegex(UserError, 'no image data returned'),
        ):
            self.providers['google']._get_client().generate_image(
                'gemini-image', 'a dot'
            )
