from __future__ import annotations

import copy
import json
from collections.abc import Sequence
from unittest.mock import MagicMock, patch

import requests

from odoo.exceptions import UserError
from odoo.tools import mute_logger

from odoo.addons.muk_ai.providers.google import GoogleProvider
from odoo.addons.muk_ai.tests.common import AITestCommon


class TestAiGoogleProvider(AITestCommon):
    """Verify the Google provider request building, parsing, and streaming."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    def setUp(self) -> None:
        super().setUp()
        self.provider = self.provider_google

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _parts_body(self, parts: list[dict]) -> dict:
        """Wrap response parts in a Gemini ``generateContent`` response body."""
        return {
            'candidates': [
                {
                    'content': {'role': 'model', 'parts': parts},
                    'finishReason': 'STOP',
                }
            ],
            'usageMetadata': {
                'promptTokenCount': 3,
                'candidatesTokenCount': 2,
                'cachedContentTokenCount': 0,
            },
        }

    def _function_call_part(
        self,
        name: str,
        args: dict,
        signature: str | None = None,
    ) -> dict:
        """Build a ``functionCall`` response part, signed when Gemini 3 would sign it.

        :param signature: the ``thoughtSignature`` the wire delivers next to
            the call, omitted for the generations that emit none
        """
        part = {'functionCall': {'name': name, 'args': args}}
        if signature:
            part['thoughtSignature'] = signature
        return part

    def _carry_item(
        self,
        name: str,
        args: dict,
        call_id: str,
        signature: str | None = None,
    ) -> dict:
        """Build a stored function-call item as a Google round would carry it.

        :param signature: the ``thoughtSignature`` the stored part replays,
            omitted for a call the model left unsigned
        """
        item = {
            'type': 'function_call',
            'name': name,
            'arguments': json.dumps(args),
            'call_id': call_id,
        }
        if signature:
            item['provider_state'] = {
                'google': {'parts': [self._function_call_part(name, args, signature)]}
            }
        return item

    def _builtin_part(self, key: str, signature: str) -> dict:
        """Build a signed server-side built-in invocation part.

        :param key: the wire key of the part, ``toolCall`` for the invocation
            and ``toolResponse`` for what the built-in tool answered
        """
        return {key: {'name': 'google_search'}, 'thoughtSignature': signature}

    def _carried_parts(self, carry: dict) -> list:
        """Return the verbatim Google parts a carry item replays on the next round."""
        return (carry.get('provider_state') or {}).get('google', {}).get('parts') or []

    def _google_body(
        self,
        text: str = 'ok',
        function_calls: Sequence[tuple[str, dict]] = (),
    ) -> dict:
        """Build a Gemini ``generateContent`` response body.

        :param function_calls: ``(tool name, arguments)`` pairs emitted as
            ``functionCall`` parts next to the text part.
        """
        parts = [{'text': text}] if text else []
        parts.extend(self._function_call_part(*call) for call in function_calls)
        return self._parts_body(parts)

    def _sse_lines(self, payloads: Sequence[dict]) -> list[str]:
        """Render the payloads as the ``data:`` lines of an SSE stream."""
        lines = []
        for payload in payloads:
            lines.append('data: ' + json.dumps(payload))
            lines.append('')
        return lines

    def _run_request(self, payload: dict, **kwargs) -> tuple[dict, dict]:
        """Run a non-streaming request against a canned response body.

        :return: the provider result and the request body that was sent
        """
        captured = {}

        def fake_post(url, **post_kwargs):
            captured['body'] = post_kwargs.get('json')
            return self._mock_http_response(payload)

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            result = self.provider._request_responses(**kwargs)
        return result, captured['body']

    def _run_stream(
        self, payloads: Sequence[dict], **kwargs
    ) -> tuple[dict, list[tuple[str, dict]], dict]:
        """Run a streaming request over canned SSE payloads.

        :return: the provider result, the forwarded deltas, and the sent body
        """
        response = MagicMock()
        response.iter_lines.return_value = iter(self._sse_lines(payloads))
        response.raise_for_status.return_value = None
        captured = {}
        deltas = []

        def fake_post(url, **post_kwargs):
            captured['body'] = post_kwargs.get('json')
            return response

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            result = self.provider._request_responses(
                on_delta=lambda kind, payload: deltas.append((kind, payload)),
                **kwargs,
            )
        return result, deltas, captured['body']

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_thinking_level_sent_for_low_effort_on_gemini_3(self):
        captured = {}

        def fake_post(url, **kwargs):
            captured['body'] = kwargs.get('json')
            return self._mock_http_response(self._google_body('ok'))

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            self.provider._request_responses(
                inputs=[
                    {'role': 'user', 'content': [{'type': 'input_text', 'text': 'hi'}]}
                ],
                model='gemini-3.8-flash',
                reasoning_effort='low',
            )
        self.assertEqual(
            captured['body']['generationConfig']['thinkingConfig'],
            {'includeThoughts': True, 'thinkingLevel': 'low'},
        )

    def test_unset_effort_keeps_model_default_thinking(self):
        captured = {}

        def fake_post(url, **kwargs):
            captured['body'] = kwargs.get('json')
            return self._mock_http_response(self._google_body('ok'))

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            self.provider._request_responses(
                inputs=[
                    {'role': 'user', 'content': [{'type': 'input_text', 'text': 'hi'}]}
                ],
                model='gemini-3.8-flash',
            )
        self.assertEqual(
            captured['body']['generationConfig']['thinkingConfig'],
            {'includeThoughts': True},
        )

    def test_extreme_efforts_map_to_supported_levels(self):
        captured = {}

        def fake_post(url, **kwargs):
            captured['body'] = kwargs.get('json')
            return self._mock_http_response(self._google_body('ok'))

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            self.provider._request_responses(
                inputs=[
                    {'role': 'user', 'content': [{'type': 'input_text', 'text': 'hi'}]}
                ],
                model='gemini-3.8-flash',
                reasoning_effort='max',
            )
        self.assertEqual(
            captured['body']['generationConfig']['thinkingConfig'],
            {'includeThoughts': True, 'thinkingLevel': 'high'},
        )
        with patch.object(requests.Session, 'post', side_effect=fake_post):
            self.provider._request_responses(
                inputs=[
                    {'role': 'user', 'content': [{'type': 'input_text', 'text': 'hi'}]}
                ],
                model='gemini-3.8-flash',
                reasoning_effort='minimal',
            )
        self.assertEqual(
            captured['body']['generationConfig']['thinkingConfig'],
            {'includeThoughts': True, 'thinkingLevel': 'low'},
        )

    @mute_logger('odoo.addons.muk_ai.providers.base')
    def test_rejected_thinking_level_is_stripped_and_served(self):
        record = self.env.ref('muk_ai.model_gemini_3_8_flash')
        bodies = []

        def fake_post(url, **kwargs):
            bodies.append(copy.deepcopy(kwargs.get('json')))
            if len(bodies) == 1:
                response = self._mock_http_response({}, status_code=400)
                response.text = 'Invalid thinking level for this model.'
                response.raise_for_status.side_effect = requests.HTTPError(
                    'bad request', response=response
                )
                return response
            return self._mock_http_response(self._google_body('ok'))

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            result = self.provider._request_responses(
                inputs=[
                    {'role': 'user', 'content': [{'type': 'input_text', 'text': 'hi'}]}
                ],
                model='gemini-3.8-flash',
                reasoning_effort='low',
            )
        self.assertEqual(len(bodies), 2)
        self.assertEqual(
            bodies[0]['generationConfig']['thinkingConfig'],
            {'includeThoughts': True, 'thinkingLevel': 'low'},
        )
        self.assertNotIn('thinkingConfig', bodies[1]['generationConfig'])
        self.assertEqual(result['text'], 'ok')
        self.assertEqual(record.reasoning_efforts, ['low', 'medium', 'high'])

    def test_thinking_level_not_sent_for_gemini_2_5(self):
        captured = {}

        def fake_post(url, **kwargs):
            captured['body'] = kwargs.get('json')
            return self._mock_http_response(self._google_body('ok'))

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            self.provider._request_responses(
                inputs=[
                    {'role': 'user', 'content': [{'type': 'input_text', 'text': 'hi'}]}
                ],
                model='gemini-2.5-flash',
                reasoning_effort='low',
            )
        thinking = captured['body']['generationConfig']['thinkingConfig']
        self.assertNotIn('thinkingLevel', thinking)

    @mute_logger('odoo.addons.muk_ai.providers.base')
    def test_thinking_error_retries_once_without_thinking_config(self):
        bodies = []

        def fake_post(url, **kwargs):
            bodies.append(json.loads(json.dumps(kwargs.get('json'))))
            if len(bodies) == 1:
                response = self._mock_http_response({})
                response.status_code = 400
                response.text = "Unknown field 'thinkingLevel' for this model."
                response.raise_for_status.side_effect = requests.HTTPError(
                    'bad request', response=response
                )
                return response
            return self._mock_http_response(self._google_body('ok'))

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            result = self.provider._request_responses(
                inputs=[
                    {'role': 'user', 'content': [{'type': 'input_text', 'text': 'hi'}]}
                ],
                model='gemini-3.8-flash',
                reasoning_effort='low',
            )
        self.assertEqual(len(bodies), 2)
        self.assertIn('thinkingConfig', bodies[0]['generationConfig'])
        self.assertNotIn('thinkingConfig', bodies[1].get('generationConfig', {}))
        self.assertEqual(result['text'], 'ok')

    def test_inputs_to_contents_splits_system_and_merges_runs(self):
        system, contents = self.provider._get_client()._inputs_to_contents(
            [
                {'role': 'system', 'content': [{'type': 'input_text', 'text': 'sys1'}]},
                {'role': 'system', 'content': [{'type': 'input_text', 'text': 'sys2'}]},
                {'role': 'user', 'content': [{'type': 'input_text', 'text': 'hi'}]},
                self._carry_item('t', {'a': 1}, 'c1', 'sig-a'),
                {'type': 'function_call_output', 'call_id': 'c1', 'output': '"ok"'},
                {'role': 'user', 'content': [{'type': 'input_text', 'text': 'next'}]},
            ]
        )
        self.assertIn('sys1', system)
        self.assertIn('sys2', system)
        self.assertEqual(contents[0]['role'], 'user')
        self.assertEqual(contents[0]['parts'][0], {'text': 'hi'})
        self.assertEqual(contents[1]['role'], 'model')
        self.assertEqual(contents[1]['parts'][0]['functionCall']['name'], 't')
        self.assertEqual(contents[1]['parts'][0]['functionCall']['args'], {'a': 1})
        self.assertEqual(contents[2]['role'], 'user')
        self.assertEqual(contents[2]['parts'][0]['functionResponse']['name'], 't')
        self.assertEqual(contents[2]['parts'][1], {'text': 'next'})

    def test_function_response_carries_lookedup_name(self):
        _system, contents = self.provider._get_client()._inputs_to_contents(
            [
                self._carry_item('list_modules', {}, 'cX', 'sig-a'),
                {
                    'type': 'function_call_output',
                    'call_id': 'cX',
                    'output': '{"ok": true}',
                },
            ]
        )
        self.assertEqual(
            contents[1]['parts'][0]['functionResponse']['name'],
            'list_modules',
        )
        self.assertEqual(
            contents[1]['parts'][0]['functionResponse']['response'],
            {'ok': True},
        )

    def test_request_sends_messages_shape(self):
        captured = {}

        def fake_post(url, **kwargs):
            captured['url'] = url
            captured['body'] = kwargs.get('json')
            captured['headers'] = kwargs.get('headers')
            return self._mock_http_response(self._google_body('hello'))

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            result = self.provider._request_responses(
                inputs=[
                    {
                        'role': 'system',
                        'content': [{'type': 'input_text', 'text': 'be brief'}],
                    },
                    {'role': 'user', 'content': [{'type': 'input_text', 'text': 'hi'}]},
                ],
                tools_schema=[
                    {
                        'type': 'function',
                        'name': 'x',
                        'description': 'd',
                        'parameters': {'type': 'object', 'properties': {}},
                    }
                ],
            )
        self.assertTrue(captured['url'].endswith(':generateContent'))
        default_model = self.provider.default_chat_model_id.technical_name
        self.assertIn(f'/models/{default_model}', captured['url'])
        self.assertEqual(
            captured['body']['systemInstruction']['parts'][0]['text'], 'be brief'
        )
        self.assertEqual(captured['body']['contents'][0]['role'], 'user')
        self.assertEqual(
            captured['body']['tools'][0]['functionDeclarations'][0]['name'],
            'x',
        )
        self.assertEqual(captured['body']['generationConfig']['maxOutputTokens'], 4096)
        self.assertEqual(captured['headers']['x-goog-api-key'], 'test-key')
        self.assertEqual(result['text'], 'hello')
        self.assertEqual(result['tool_calls'], [])

    def test_request_parses_function_call(self):
        def fake_post(url, **kwargs):
            return self._mock_http_response(
                self._google_body(
                    text='',
                    function_calls=[('list_modules', {'installed_only': True})],
                )
            )

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            result = self.provider._request_responses(inputs=[])
        self.assertEqual(len(result['tool_calls']), 1)
        self.assertEqual(result['tool_calls'][0]['name'], 'list_modules')
        self.assertEqual(result['tool_calls'][0]['arguments'], {'installed_only': True})
        self.assertTrue(result['tool_calls'][0]['call_id'].startswith('call_google_'))
        self.assertEqual(result['carry_inputs'][0]['type'], 'function_call')

    def test_stream_emits_text_and_tool_deltas(self):
        sse = self._sse_lines(
            [
                {
                    'candidates': [
                        {'content': {'role': 'model', 'parts': [{'text': 'Hel'}]}}
                    ]
                },
                {
                    'candidates': [
                        {'content': {'role': 'model', 'parts': [{'text': 'lo'}]}}
                    ]
                },
                {
                    'candidates': [
                        {
                            'content': {
                                'role': 'model',
                                'parts': [
                                    {
                                        'functionCall': {
                                            'name': 'do_x',
                                            'args': {'a': 1},
                                        }
                                    },
                                ],
                            }
                        }
                    ]
                },
                {'usageMetadata': {'promptTokenCount': 7, 'candidatesTokenCount': 4}},
            ]
        )
        response = MagicMock()
        response.iter_lines.return_value = iter(sse)
        response.raise_for_status.return_value = None

        def fake_post(url, **kwargs):
            return response

        deltas = []

        def on_delta(kind, payload):
            deltas.append((kind, payload))

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            result = self.provider._request_responses(inputs=[], on_delta=on_delta)
        text_deltas = [p['delta'] for (k, p) in deltas if k == 'text']
        tool_starts = [p for (k, p) in deltas if k == 'tool_start']
        tool_args = [p for (k, p) in deltas if k == 'tool_args']
        self.assertEqual(text_deltas, ['Hel', 'lo'])
        self.assertEqual(tool_starts[0]['name'], 'do_x')
        self.assertEqual(json.loads(tool_args[0]['delta']), {'a': 1})
        self.assertEqual(result['text'], 'Hello')
        self.assertEqual(len(result['tool_calls']), 1)
        self.assertEqual(result['tool_calls'][0]['arguments'], {'a': 1})
        self.assertEqual(result['usage']['input_tokens'], 7)
        self.assertEqual(result['usage']['output_tokens'], 4)

    def test_google_usage_counts_thoughts_tokens_as_output(self):
        body = self._google_body('ok')
        body['usageMetadata'] = {
            'promptTokenCount': 44,
            'candidatesTokenCount': 207,
            'thoughtsTokenCount': 505,
            'totalTokenCount': 756,
        }
        with patch.object(
            requests.Session, 'post', return_value=self._mock_http_response(body)
        ):
            result = self.provider._request_responses(inputs=[])
        usage = result['usage']
        self.assertEqual(usage['input_tokens'], 44)
        self.assertEqual(usage['output_tokens'], 712)
        self.assertEqual(
            usage['input_tokens'] + usage['output_tokens'],
            body['usageMetadata']['totalTokenCount'],
        )

    def test_google_stream_usage_counts_thoughts_tokens_as_output(self):
        sse = self._sse_lines(
            [
                {
                    'candidates': [
                        {'content': {'role': 'model', 'parts': [{'text': 'Hello'}]}}
                    ],
                    'usageMetadata': {
                        'promptTokenCount': 44,
                        'candidatesTokenCount': 100,
                        'thoughtsTokenCount': 553,
                        'totalTokenCount': 697,
                    },
                },
                {
                    'usageMetadata': {
                        'promptTokenCount': 44,
                        'candidatesTokenCount': 194,
                        'thoughtsTokenCount': 553,
                        'totalTokenCount': 791,
                    }
                },
            ]
        )
        response = MagicMock()
        response.iter_lines.return_value = iter(sse)
        response.raise_for_status.return_value = None
        with patch.object(requests.Session, 'post', return_value=response):
            result = self.provider._request_responses(
                inputs=[], on_delta=lambda kind, payload: None
            )
        usage = result['usage']
        self.assertEqual(usage['input_tokens'], 44)
        self.assertEqual(usage['output_tokens'], 747)
        self.assertEqual(usage['input_tokens'] + usage['output_tokens'], 791)

    def test_google_max_tokens_finish_appends_truncation_notice(self):
        body = self._google_body('partial')
        body['candidates'][0]['finishReason'] = 'MAX_TOKENS'
        with patch.object(
            requests.Session, 'post', return_value=self._mock_http_response(body)
        ):
            result = self.provider._request_responses(inputs=[])
        self.assertIn('partial', result['text'])
        self.assertIn('Max Tokens', result['text'])
        self.assertEqual(result['usage']['output_tokens'], 2)

    def test_google_stream_max_tokens_finish_appends_truncation_notice(self):
        sse = self._sse_lines(
            [
                {
                    'candidates': [
                        {'content': {'role': 'model', 'parts': [{'text': 'partial'}]}}
                    ]
                },
                {
                    'candidates': [
                        {
                            'finishReason': 'MAX_TOKENS',
                            'content': {'role': 'model', 'parts': []},
                        }
                    ],
                    'usageMetadata': {
                        'promptTokenCount': 7,
                        'candidatesTokenCount': 4096,
                    },
                },
            ]
        )
        response = MagicMock()
        response.iter_lines.return_value = iter(sse)
        response.raise_for_status.return_value = None
        deltas = []
        with patch.object(requests.Session, 'post', return_value=response):
            result = self.provider._request_responses(
                inputs=[],
                on_delta=lambda k, p: deltas.append((k, p)),
            )
        self.assertIn('partial', result['text'])
        self.assertIn('Max Tokens', result['text'])
        self.assertEqual(result['usage']['output_tokens'], 4096)
        text_deltas = [p['delta'] for (k, p) in deltas if k == 'text']
        self.assertTrue(any('Max Tokens' in d for d in text_deltas))

    def test_attachment_image_becomes_inline_data(self):
        captured = {}

        def fake_post(url, **kwargs):
            captured['body'] = kwargs.get('json')
            return self._mock_http_response(self._google_body('ok'))

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            self.provider._request_responses(
                inputs=[
                    {
                        'role': 'user',
                        'content': [
                            {
                                'type': 'muk_ai_attachment',
                                'strategy': 'image',
                                'mimetype': 'image/png',
                                'data_b64': 'AAA=',
                                'filename': 'p.png',
                            }
                        ],
                    }
                ],
            )
        part = captured['body']['contents'][0]['parts'][0]
        self.assertEqual(part['inlineData']['mimeType'], 'image/png')
        self.assertEqual(part['inlineData']['data'], 'AAA=')

    def test_attachment_pdf_becomes_inline_data(self):
        captured = {}

        def fake_post(url, **kwargs):
            captured['body'] = kwargs.get('json')
            return self._mock_http_response(self._google_body('ok'))

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            self.provider._request_responses(
                inputs=[
                    {
                        'role': 'user',
                        'content': [
                            {
                                'type': 'muk_ai_attachment',
                                'strategy': 'file',
                                'mimetype': 'application/pdf',
                                'data_b64': 'PDF=',
                                'filename': 'r.pdf',
                            }
                        ],
                    }
                ],
            )
        part = captured['body']['contents'][0]['parts'][0]
        self.assertEqual(part['inlineData']['mimeType'], 'application/pdf')
        self.assertEqual(part['inlineData']['data'], 'PDF=')

    def test_attachment_text_becomes_text_part_with_filename_prefix(self):
        captured = {}

        def fake_post(url, **kwargs):
            captured['body'] = kwargs.get('json')
            return self._mock_http_response(self._google_body('ok'))

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            self.provider._request_responses(
                inputs=[
                    {
                        'role': 'user',
                        'content': [
                            {
                                'type': 'muk_ai_attachment',
                                'strategy': 'inline',
                                'mimetype': 'text/plain',
                                'inline_text': 'hello\nworld',
                                'filename': 'note.txt',
                                'truncated': True,
                            }
                        ],
                    }
                ],
            )
        part = captured['body']['contents'][0]['parts'][0]
        self.assertIn('--- File: note.txt (text/plain) ---', part['text'])
        self.assertIn('hello\nworld', part['text'])
        self.assertIn('[truncated]', part['text'])

    def test_injects_google_search_tool_on_enable_web_search(self):
        captured = {}

        def fake_post(url, **kwargs):
            captured['body'] = kwargs.get('json')
            return self._mock_http_response(self._google_body('ok'))

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            self.provider._request_responses(
                inputs=[],
                enable_web_search=True,
            )
        tools = captured['body'].get('tools') or []
        self.assertTrue(any('googleSearch' in t for t in tools))

    def test_injects_code_execution_tool_on_enable_code_interpreter(self):
        captured = {}

        def fake_post(url, **kwargs):
            captured['body'] = kwargs.get('json')
            return self._mock_http_response(self._google_body('ok'))

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            self.provider._request_responses(
                inputs=[],
                enable_code_interpreter=True,
            )
        tools = captured['body'].get('tools') or []
        self.assertTrue(any('codeExecution' in t for t in tools))

    def test_generate_image_asks_for_image_output(self):
        captured = {}

        def fake_post(url, **kwargs):
            captured.update(url=url, body=kwargs.get('json'))
            return self._mock_http_response(
                {
                    'candidates': [
                        {
                            'content': {
                                'parts': [
                                    {
                                        'inlineData': {
                                            'mimeType': 'image/jpeg',
                                            'data': 'AAA=',
                                        }
                                    }
                                ]
                            }
                        }
                    ]
                }
            )

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            result = self.provider._get_client().generate_image(
                'gemini-3.1-flash-image',
                'a dot',
                {'size': '1536x1024', 'quality': 'high', 'background': None},
            )
        self.assertTrue(
            captured['url'].endswith('/models/gemini-3.1-flash-image:generateContent')
        )
        self.assertEqual(
            captured['body'],
            {
                'contents': [{'role': 'user', 'parts': [{'text': 'a dot'}]}],
                'generationConfig': {
                    'responseModalities': ['IMAGE'],
                    'imageConfig': {'aspectRatio': '3:2'},
                },
            },
        )
        self.assertEqual(
            result,
            {
                'data_b64': 'AAA=',
                'mimetype': 'image/jpeg',
                'revised_prompt': '',
                'usage': {'images': 1},
            },
        )

    def test_generate_image_without_a_size_sends_no_aspect_ratio(self):
        captured = {}

        def fake_post(url, **kwargs):
            captured['body'] = kwargs.get('json')
            return self._mock_http_response(
                {
                    'candidates': [
                        {'content': {'parts': [{'inlineData': {'data': 'AAA='}}]}}
                    ]
                }
            )

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            result = self.provider._get_client().generate_image('gemini-image', 'a dot')
        self.assertEqual(
            captured['body']['generationConfig'], {'responseModalities': ['IMAGE']}
        )
        self.assertEqual(result['mimetype'], 'image/png')

    def test_generate_image_without_image_data_raises(self):
        response = self._mock_http_response(self._google_body('I cannot draw that'))
        with (
            patch.object(requests.Session, 'post', return_value=response),
            self.assertRaises(UserError) as caught,
        ):
            self.provider._get_client().generate_image('gemini-image', 'a dot')
        self.assertIn('no image data returned', str(caught.exception))

    def test_aspect_ratio_snaps_to_the_closest_supported_one(self):
        ratio = GoogleProvider._aspect_ratio
        self.assertEqual(ratio('1024x1024'), '1:1')
        self.assertEqual(ratio('1024x1536'), '2:3')
        self.assertEqual(ratio('1920X1080'), '16:9')
        self.assertEqual(ratio('1000x900'), '1:1')
        self.assertIsNone(ratio(None))
        self.assertIsNone(ratio('large'))
        self.assertIsNone(ratio('0x10'))

    def test_text_schema_sets_response_mime_type_and_schema(self):
        captured = {}

        def fake_post(url, **kwargs):
            captured['body'] = kwargs.get('json')
            return self._mock_http_response(self._google_body('ok'))

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            self.provider._request_responses(
                inputs=[],
                text_schema={'name': 'plan', 'schema': {'type': 'object'}},
            )
        gen_cfg = captured['body']['generationConfig']
        self.assertEqual(gen_cfg['responseMimeType'], 'application/json')
        self.assertEqual(gen_cfg['responseSchema'], {'type': 'object'})

    def test_request_uses_model_kwarg(self):
        captured = {}

        def fake_post(url, **kwargs):
            captured['url'] = url
            return self._mock_http_response(self._google_body('ok'))

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            self.provider._request_responses(inputs=[], model='gemini-2.5-pro')
        self.assertIn('/models/gemini-2.5-pro', captured['url'])

    def test_request_omits_max_tokens_when_zero(self):
        self.provider.max_tokens = 0
        captured = {}

        def fake_post(url, **kwargs):
            captured['body'] = kwargs.get('json')
            return self._mock_http_response(self._google_body('ok'))

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            self.provider._request_responses(inputs=[])
        self.assertNotIn('maxOutputTokens', captured['body']['generationConfig'])

    def test_test_connection_returns_true_on_text_response(self):
        def fake_post(url, **kwargs):
            return self._mock_http_response(self._google_body('ok'))

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            self.assertTrue(self.provider._get_client().test_connection())

    def test_request_raises_on_http_error(self):
        response = self._mock_http_response({}, status_code=400)
        response.text = 'INVALID_ARGUMENT'
        response.raise_for_status.side_effect = requests.HTTPError(
            '400', response=response
        )
        with patch.object(requests.Session, 'post', return_value=response):
            with self.assertRaises(UserError):
                self.provider._request_responses(inputs=[])

    def test_request_raises_on_missing_key(self):
        self.provider.sudo().api_key = ''
        with self.assertRaises(UserError):
            self.provider._request_responses(inputs=[])

    def test_executable_code_part_renders_as_fenced_block(self):
        body = {
            'candidates': [
                {
                    'content': {
                        'role': 'model',
                        'parts': [
                            {
                                'executableCode': {
                                    'language': 'PYTHON',
                                    'code': 'print(1)',
                                }
                            },
                            {
                                'codeExecutionResult': {
                                    'outcome': 'OUTCOME_OK',
                                    'output': '1\n',
                                }
                            },
                        ],
                    }
                }
            ],
            'usageMetadata': {},
        }
        with patch.object(
            requests.Session, 'post', return_value=self._mock_http_response(body)
        ):
            result = self.provider._request_responses(inputs=[])
        self.assertIn('```python', result['text'])
        self.assertIn('print(1)', result['text'])
        self.assertIn('1\n', result['text'])

    def test_function_call_carries_its_signed_part(self):
        body = self._parts_body(
            [self._function_call_part('search_read', {'model': 'res.partner'}, 'sig-a')]
        )
        result, _sent = self._run_request(body, inputs=[])
        carry = result['carry_inputs'][0]
        self.assertEqual(carry['type'], 'function_call')
        self.assertEqual(
            self._carried_parts(carry),
            [
                self._function_call_part(
                    'search_read', {'model': 'res.partner'}, 'sig-a'
                )
            ],
        )

    def test_streamed_function_call_carries_its_signed_part(self):
        result, _deltas, _sent = self._run_stream(
            [
                {
                    'candidates': [
                        {
                            'content': {
                                'role': 'model',
                                'parts': [
                                    self._function_call_part(
                                        'search_read',
                                        {'model': 'res.partner'},
                                        'sig-a',
                                    )
                                ],
                            }
                        }
                    ]
                },
            ],
            inputs=[],
        )
        carry = result['carry_inputs'][0]
        self.assertEqual(carry['type'], 'function_call')
        self.assertEqual(self._carried_parts(carry)[0].get('thoughtSignature'), 'sig-a')

    def test_unsigned_function_call_carries_an_unsigned_part(self):
        body = self._parts_body(
            [self._function_call_part('search_read', {'model': 'res.partner'})]
        )
        result, _sent = self._run_request(body, inputs=[])
        self.assertNotIn(
            'thoughtSignature', self._carried_parts(result['carry_inputs'][0])[0]
        )

    def test_streamed_unsigned_function_call_carries_an_unsigned_part(self):
        result, _deltas, _sent = self._run_stream(
            [
                {
                    'candidates': [
                        {
                            'content': {
                                'role': 'model',
                                'parts': [
                                    self._function_call_part(
                                        'search_read', {'model': 'res.partner'}
                                    )
                                ],
                            }
                        }
                    ]
                },
            ],
            inputs=[],
        )
        self.assertNotIn(
            'thoughtSignature', self._carried_parts(result['carry_inputs'][0])[0]
        )

    def test_parallel_function_calls_keep_their_own_signature(self):
        body = self._parts_body(
            [
                self._function_call_part('search_read', {'model': 'a'}, 'sig-a'),
                self._function_call_part('read_group', {'model': 'b'}, 'sig-b'),
                self._function_call_part('search_count', {'model': 'c'}),
            ]
        )
        result, _sent = self._run_request(body, inputs=[])
        self.assertEqual(
            [
                self._carried_parts(carry)[0].get('thoughtSignature')
                for carry in result['carry_inputs']
            ],
            ['sig-a', 'sig-b', None],
        )

    def test_streamed_parallel_function_calls_keep_their_own_signature(self):
        result, _deltas, _sent = self._run_stream(
            [
                {
                    'candidates': [
                        {
                            'content': {
                                'role': 'model',
                                'parts': [
                                    self._function_call_part(
                                        'search_read', {'model': 'a'}, 'sig-a'
                                    ),
                                    self._function_call_part(
                                        'read_group', {'model': 'b'}, 'sig-b'
                                    ),
                                    self._function_call_part(
                                        'search_count', {'model': 'c'}
                                    ),
                                ],
                            }
                        }
                    ]
                },
            ],
            inputs=[],
        )
        self.assertEqual(
            [
                self._carried_parts(carry)[0].get('thoughtSignature')
                for carry in result['carry_inputs']
            ],
            ['sig-a', 'sig-b', None],
        )

    def test_carried_signed_part_is_echoed_on_the_next_round(self):
        _result, sent = self._run_request(
            self._google_body('done'),
            inputs=[
                {
                    'role': 'user',
                    'content': [{'type': 'input_text', 'text': 'how many partners?'}],
                },
                self._carry_item(
                    'search_read',
                    {'model': 'res.partner'},
                    'call_google_1',
                    'sig-a',
                ),
                {
                    'type': 'function_call_output',
                    'call_id': 'call_google_1',
                    'output': '{"count": 3}',
                },
            ],
        )
        model_parts = next(c for c in sent['contents'] if c['role'] == 'model')['parts']
        self.assertEqual(model_parts[0]['functionCall']['name'], 'search_read')
        self.assertEqual(model_parts[0]['thoughtSignature'], 'sig-a')

    def test_a_call_this_adapter_never_signed_is_replayed_as_transcript_text(self):
        _result, sent = self._run_request(
            self._google_body('done'),
            inputs=[
                {
                    'type': 'function_call',
                    'name': 'search_read',
                    'arguments': '{"model": "res.partner"}',
                    'call_id': 'call_openai_1',
                },
                {
                    'type': 'function_call_output',
                    'call_id': 'call_openai_1',
                    'output': '{"count": 3}',
                },
            ],
        )
        model_parts = next(c for c in sent['contents'] if c['role'] == 'model')['parts']
        self.assertEqual(
            model_parts[0],
            {'text': '[tool call] search_read({"model": "res.partner"})'},
        )
        user_parts = next(c for c in sent['contents'] if c['role'] == 'user')['parts']
        self.assertEqual(
            user_parts[0],
            {'text': '[tool result] search_read: {"count": 3}'},
        )
        self.assertNotIn('functionCall', json.dumps(sent))
        self.assertNotIn('functionResponse', json.dumps(sent))

    def test_parallel_carried_signatures_are_echoed_one_per_call(self):
        _result, sent = self._run_request(
            self._google_body('done'),
            inputs=[
                self._carry_item('search_read', {}, 'call_google_1', 'sig-a'),
                self._carry_item('read_group', {}, 'call_google_2', 'sig-b'),
            ],
        )
        model_parts = next(c for c in sent['contents'] if c['role'] == 'model')['parts']
        self.assertEqual(
            [part['thoughtSignature'] for part in model_parts],
            ['sig-a', 'sig-b'],
        )

    def test_round_trip_keeps_the_signature_through_a_streamed_call(self):
        first, _deltas, _sent = self._run_stream(
            [
                {
                    'candidates': [
                        {
                            'content': {
                                'role': 'model',
                                'parts': [
                                    self._function_call_part(
                                        'search_read', {'model': 'res.partner'}, 'sig-a'
                                    )
                                ],
                            }
                        }
                    ]
                },
            ],
            inputs=[],
        )
        _result, sent = self._run_request(
            self._google_body('done'),
            inputs=[
                *first['carry_inputs'],
                {
                    'type': 'function_call_output',
                    'call_id': first['tool_calls'][0]['call_id'],
                    'output': '{"count": 3}',
                },
            ],
        )
        model_parts = next(c for c in sent['contents'] if c['role'] == 'model')['parts']
        self.assertEqual(model_parts[0]['thoughtSignature'], 'sig-a')

    def test_builtin_tool_beside_functions_opts_into_server_side_invocations(self):
        _result, sent = self._run_request(
            self._google_body('ok'),
            inputs=[],
            tools_schema=[{'name': 'search_read', 'description': 'read'}],
            enable_web_search=True,
            model='gemini-3.8-flash',
        )
        self.assertEqual(
            sent['toolConfig'],
            {'includeServerSideToolInvocations': True},
        )
        self.assertTrue(any('googleSearch' in tool for tool in sent['tools']))
        self.assertTrue(any('functionDeclarations' in tool for tool in sent['tools']))

    def test_code_interpreter_beside_functions_opts_into_server_side_invocations(self):
        _result, sent = self._run_request(
            self._google_body('ok'),
            inputs=[],
            tools_schema=[{'name': 'search_read', 'description': 'read'}],
            enable_code_interpreter=True,
            model='gemini-3.8-flash',
        )
        self.assertEqual(
            sent['toolConfig'],
            {'includeServerSideToolInvocations': True},
        )

    def test_builtin_tool_without_functions_sends_no_tool_config(self):
        _result, sent = self._run_request(
            self._google_body('ok'),
            inputs=[],
            enable_web_search=True,
            model='gemini-3.8-flash',
        )
        self.assertNotIn('toolConfig', sent)

    def test_functions_without_builtin_tool_send_no_tool_config(self):
        _result, sent = self._run_request(
            self._google_body('ok'),
            inputs=[],
            tools_schema=[{'name': 'search_read', 'description': 'read'}],
            model='gemini-3.8-flash',
        )
        self.assertNotIn('toolConfig', sent)

    def test_gemini_2_5_never_opts_into_server_side_invocations(self):
        _result, sent = self._run_request(
            self._google_body('ok'),
            inputs=[],
            tools_schema=[{'name': 'search_read', 'description': 'read'}],
            enable_web_search=True,
            model='gemini-2.5-flash',
        )
        self.assertNotIn('toolConfig', sent)
        client = self.provider._get_client()
        self.assertFalse(client.serves_builtin_tools('gemini-2.5-flash'))
        self.assertTrue(client.serves_builtin_tools('gemini-3.8-flash'))

    def test_thought_parts_stream_as_reasoning_and_stay_out_of_the_answer(self):
        result, deltas, _sent = self._run_stream(
            [
                {
                    'candidates': [
                        {
                            'content': {
                                'role': 'model',
                                'parts': [{'thought': True, 'text': 'weighing it'}],
                            }
                        }
                    ]
                },
                {
                    'candidates': [
                        {'content': {'role': 'model', 'parts': [{'text': 'answer'}]}}
                    ]
                },
            ],
            inputs=[],
        )
        self.assertEqual(
            [payload['delta'] for kind, payload in deltas if kind == 'reasoning'],
            ['weighing it'],
        )
        self.assertEqual(result['text'], 'answer')
        self.assertEqual(result['carry_inputs'][0]['content'][0]['text'], 'answer')

    def test_thought_parts_stay_out_of_the_answer_without_streaming(self):
        body = self._parts_body(
            [{'thought': True, 'text': 'weighing it'}, {'text': 'answer'}]
        )
        result, _sent = self._run_request(body, inputs=[])
        self.assertEqual(result['text'], 'answer')

    def test_generate_image_uses_the_image_timeout(self):
        captured = {}

        def fake_post(url, **kwargs):
            captured['timeout'] = kwargs.get('timeout')
            return self._mock_http_response(
                {
                    'candidates': [
                        {
                            'content': {
                                'parts': [
                                    {
                                        'inlineData': {
                                            'mimeType': 'image/png',
                                            'data': 'AAA=',
                                        }
                                    }
                                ]
                            }
                        }
                    ]
                }
            )

        self.provider.sudo().write({'request_timeout': 45, 'image_timeout': 180})
        with patch.object(requests.Session, 'post', side_effect=fake_post):
            self.provider._get_client().generate_image(
                'gemini-3.1-flash-image', 'a dot'
            )
        self.assertEqual(captured['timeout'], 180)

    def test_builtin_parts_ride_along_with_the_function_call(self):
        body = self._parts_body(
            [
                self._builtin_part('toolCall', 'sig-search'),
                self._function_call_part('search_read', {'model': 'res.partner'}),
                self._builtin_part('toolResponse', 'sig-result'),
            ]
        )
        result, _sent = self._run_request(body, inputs=[])
        self.assertEqual(len(result['carry_inputs']), 1)
        self.assertEqual(
            [
                next(iter(part))
                for part in self._carried_parts(result['carry_inputs'][0])
            ],
            ['toolCall', 'functionCall', 'toolResponse'],
        )

    def test_streamed_builtin_parts_ride_along_with_the_function_call(self):
        result, _deltas, _sent = self._run_stream(
            [
                {
                    'candidates': [
                        {
                            'content': {
                                'role': 'model',
                                'parts': [
                                    self._builtin_part('toolCall', 'sig-search'),
                                    self._function_call_part('search_read', {}),
                                ],
                            }
                        }
                    ]
                },
                {
                    'candidates': [
                        {
                            'content': {
                                'role': 'model',
                                'parts': [
                                    self._builtin_part('toolResponse', 'sig-result')
                                ],
                            }
                        }
                    ]
                },
            ],
            inputs=[],
        )
        self.assertEqual(
            [
                next(iter(part))
                for part in self._carried_parts(result['carry_inputs'][0])
            ],
            ['toolCall', 'functionCall', 'toolResponse'],
        )

    def test_builtin_parts_are_echoed_around_the_call_on_the_next_round(self):
        first, _sent = self._run_request(
            self._parts_body(
                [
                    self._builtin_part('toolCall', 'sig-search'),
                    self._function_call_part('search_read', {'model': 'res.partner'}),
                    self._builtin_part('toolResponse', 'sig-result'),
                ]
            ),
            inputs=[],
        )
        _result, sent = self._run_request(
            self._google_body('done'),
            inputs=[
                *first['carry_inputs'],
                {
                    'type': 'function_call_output',
                    'call_id': first['tool_calls'][0]['call_id'],
                    'output': '{"count": 3}',
                },
            ],
        )
        model_parts = next(c for c in sent['contents'] if c['role'] == 'model')['parts']
        self.assertEqual(
            model_parts,
            [
                self._builtin_part('toolCall', 'sig-search'),
                self._function_call_part('search_read', {'model': 'res.partner'}),
                self._builtin_part('toolResponse', 'sig-result'),
            ],
        )

    def test_a_builtin_turn_without_a_call_carries_no_state(self):
        body = self._parts_body(
            [
                self._builtin_part('toolCall', 'sig-search'),
                {'text': 'the answer'},
                self._builtin_part('toolResponse', 'sig-result'),
            ]
        )
        result, _sent = self._run_request(body, inputs=[])
        self.assertEqual(result['text'], 'the answer')
        self.assertEqual(len(result['carry_inputs']), 1)
        self.assertNotIn('provider_state', result['carry_inputs'][0])
