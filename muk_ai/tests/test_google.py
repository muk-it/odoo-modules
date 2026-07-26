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

    def _google_body(
        self,
        text: str = 'ok',
        function_calls: Sequence[tuple[str, dict]] = (),
    ) -> dict:
        """Build a Gemini ``generateContent`` response body.

        :param function_calls: ``(tool name, arguments)`` pairs emitted as
            ``functionCall`` parts next to the text part.
        """
        parts = []
        if text:
            parts.append({'text': text})
        for name, args in function_calls:
            parts.append({'functionCall': {'name': name, 'args': args}})
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

    def _sse_lines(self, payloads: Sequence[dict]) -> list[str]:
        """Render the payloads as the ``data:`` lines of an SSE stream."""
        lines = []
        for payload in payloads:
            lines.append('data: ' + json.dumps(payload))
            lines.append('')
        return lines

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
                model='gemini-3-flash-preview',
                reasoning_effort='low',
            )
        self.assertEqual(
            captured['body']['generationConfig']['thinkingConfig'],
            {'thinkingLevel': 'low'},
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
                model='gemini-3-flash-preview',
            )
        config = captured['body'].get('generationConfig') or {}
        self.assertNotIn('thinkingConfig', config)

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
                model='gemini-3-flash-preview',
                reasoning_effort='max',
            )
        self.assertEqual(
            captured['body']['generationConfig']['thinkingConfig'],
            {'thinkingLevel': 'high'},
        )
        with patch.object(requests.Session, 'post', side_effect=fake_post):
            self.provider._request_responses(
                inputs=[
                    {'role': 'user', 'content': [{'type': 'input_text', 'text': 'hi'}]}
                ],
                model='gemini-3-flash-preview',
                reasoning_effort='minimal',
            )
        self.assertEqual(
            captured['body']['generationConfig']['thinkingConfig'],
            {'thinkingLevel': 'low'},
        )

    @mute_logger('odoo.addons.muk_ai.providers.base')
    def test_rejected_thinking_level_is_stripped_and_served(self):
        record = self.env.ref('muk_ai.model_gemini_3_flash_preview')
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
                model='gemini-3-flash-preview',
                reasoning_effort='low',
            )
        self.assertEqual(len(bodies), 2)
        self.assertEqual(
            bodies[0]['generationConfig']['thinkingConfig'],
            {'thinkingLevel': 'low'},
        )
        self.assertNotIn('thinkingConfig', bodies[1]['generationConfig'])
        self.assertEqual(result['text'], 'ok')
        self.assertEqual(record.reasoning_efforts, ['low', 'high'])

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
        config = captured['body'].get('generationConfig') or {}
        self.assertNotIn('thinkingConfig', config)

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
                model='gemini-3-flash-preview',
                reasoning_effort='low',
            )
        self.assertEqual(len(bodies), 2)
        self.assertIn('thinkingConfig', bodies[0]['generationConfig'])
        self.assertNotIn('thinkingConfig', bodies[1].get('generationConfig', {}))
        self.assertEqual(result['text'], 'ok')

    def test_inputs_to_contents_splits_system_and_merges_runs(self):
        system, contents = GoogleProvider._inputs_to_contents(
            [
                {'role': 'system', 'content': [{'type': 'input_text', 'text': 'sys1'}]},
                {'role': 'system', 'content': [{'type': 'input_text', 'text': 'sys2'}]},
                {'role': 'user', 'content': [{'type': 'input_text', 'text': 'hi'}]},
                {
                    'type': 'function_call',
                    'name': 't',
                    'arguments': '{"a": 1}',
                    'call_id': 'c1',
                },
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
        _system, contents = GoogleProvider._inputs_to_contents(
            [
                {
                    'type': 'function_call',
                    'name': 'list_modules',
                    'arguments': '{}',
                    'call_id': 'cX',
                },
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
        default_model = self.provider.default_model_id.technical_name
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

    def test_switches_to_image_model_on_enable_image_generation(self):
        captured = {}

        def fake_post(url, **kwargs):
            captured['url'] = url
            return self._mock_http_response(self._google_body('ok'))

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            self.provider._request_responses(
                inputs=[],
                enable_image_generation=True,
            )
        self.assertIn('/models/gemini-2.5-flash-image', captured['url'])

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
        self.assertNotIn('generationConfig', captured['body'])

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

    def test_inline_data_in_response_renders_as_markdown_image(self):
        body = {
            'candidates': [
                {
                    'content': {
                        'role': 'model',
                        'parts': [
                            {'inlineData': {'mimeType': 'image/png', 'data': 'AAA='}},
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
        self.assertIn('data:image/png;base64,AAA=', result['text'])

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
