import base64
import json
from unittest.mock import MagicMock, patch

import requests

from odoo.exceptions import UserError

from .common import MistralTestCommon
from odoo.addons.muk_ai_mistral.providers.mistral import (
    REQUEST_ATTEMPTS,
    STREAM_ATTEMPTS,
    TOOL_NAME_PREFIX,
    MistralProvider,
)


class TestAiMistralProvider(MistralTestCommon):
    """Exercise the Mistral provider request, parsing and streaming paths."""

    # ----------------------------------------------------------
    # Inputs
    # ----------------------------------------------------------

    def test_inputs_to_entries_splits_system_and_maps_roles(self):
        instructions, entries = MistralProvider._inputs_to_entries(
            [
                {
                    'role': 'system',
                    'content': [{'type': 'input_text', 'text': 'be brief'}],
                },
                {'role': 'user', 'content': [{'type': 'input_text', 'text': 'hi'}]},
                {
                    'type': 'function_call',
                    'name': 't',
                    'arguments': '{"a": 1}',
                    'call_id': 'c1',
                },
                {'type': 'function_call_output', 'call_id': 'c1', 'output': '"ok"'},
                {
                    'role': 'assistant',
                    'content': [{'type': 'output_text', 'text': 'done'}],
                },
            ]
        )
        self.assertEqual(instructions, 'be brief')
        self.assertEqual(
            entries[0],
            {
                'object': 'entry',
                'type': 'message.input',
                'role': 'user',
                'content': 'hi',
            },
        )
        self.assertEqual(entries[1]['type'], 'function.call')
        self.assertEqual(entries[1]['tool_call_id'], 'c1')
        self.assertEqual(entries[1]['name'], 't')
        self.assertEqual(entries[1]['arguments'], '{"a": 1}')
        self.assertEqual(
            entries[2],
            {
                'object': 'entry',
                'type': 'function.result',
                'tool_call_id': 'c1',
                'result': '"ok"',
            },
        )
        self.assertEqual(
            entries[3],
            {
                'object': 'entry',
                'type': 'message.output',
                'role': 'assistant',
                'content': 'done',
            },
        )

    def test_function_result_serialises_non_string_output(self):
        _instructions, entries = MistralProvider._inputs_to_entries(
            [
                {
                    'type': 'function_call_output',
                    'call_id': 'c1',
                    'output': {'ok': True},
                },
            ]
        )
        self.assertEqual(json.loads(entries[0]['result']), {'ok': True})

    # ----------------------------------------------------------
    # Request
    # ----------------------------------------------------------

    def test_request_sends_conversations_shape(self):
        captured = {}

        def fake_post(url, **kwargs):
            captured['url'] = url
            captured['body'] = kwargs.get('json')
            captured['headers'] = kwargs.get('headers')
            return self._mock_http_response(self._text_response('hello'))

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
        self.assertTrue(captured['url'].endswith('/conversations'))
        self.assertIn('https://api.mistral.ai/v1', captured['url'])
        self.assertEqual(captured['body']['model'], 'mistral-medium-latest')
        self.assertFalse(captured['body']['store'])
        self.assertEqual(captured['body']['instructions'], 'be brief')
        self.assertEqual(captured['body']['inputs'][0]['type'], 'message.input')
        self.assertEqual(captured['body']['tools'][0]['function']['name'], 'x')
        self.assertEqual(captured['body']['completion_args']['max_tokens'], 4096)
        self.assertEqual(captured['headers']['Authorization'], 'Bearer test-key')
        self.assertEqual(result['text'], 'hello')
        self.assertEqual(result['tool_calls'], [])

    def test_request_uses_model_kwarg(self):
        captured = {}

        def fake_post(url, **kwargs):
            captured['body'] = kwargs.get('json')
            return self._mock_http_response(self._text_response('ok'))

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            self.provider._request_responses(inputs=[], model='mistral-large-latest')
        self.assertEqual(captured['body']['model'], 'mistral-large-latest')

    def test_request_omits_completion_args_when_no_max_tokens_or_schema(self):
        self.provider.max_tokens = 0
        captured = {}

        def fake_post(url, **kwargs):
            captured['body'] = kwargs.get('json')
            return self._mock_http_response(self._text_response('ok'))

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            self.provider._request_responses(inputs=[])
        self.assertNotIn('completion_args', captured['body'])

    def test_text_schema_sets_response_format(self):
        captured = {}

        def fake_post(url, **kwargs):
            captured['body'] = kwargs.get('json')
            return self._mock_http_response(self._text_response('ok'))

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            self.provider._request_responses(
                inputs=[],
                text_schema={'name': 'plan', 'schema': {'type': 'object'}},
            )
        fmt = captured['body']['completion_args']['response_format']
        self.assertEqual(fmt['type'], 'json_schema')
        self.assertEqual(fmt['json_schema']['name'], 'plan')
        self.assertEqual(fmt['json_schema']['schema'], {'type': 'object'})

    def test_request_parses_function_call(self):
        def fake_post(url, **kwargs):
            return self._mock_http_response(
                self._conv_response(
                    [
                        self._function_call(
                            '6TI17yZkV', 'list_modules', {'installed_only': True}
                        ),
                    ]
                )
            )

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            result = self.provider._request_responses(inputs=[])
        self.assertEqual(len(result['tool_calls']), 1)
        self.assertEqual(result['tool_calls'][0]['name'], 'list_modules')
        self.assertEqual(result['tool_calls'][0]['arguments'], {'installed_only': True})
        self.assertEqual(result['tool_calls'][0]['call_id'], '6TI17yZkV')
        self.assertEqual(result['carry_inputs'][0]['type'], 'function_call')
        self.assertEqual(result['carry_inputs'][0]['call_id'], '6TI17yZkV')

    def test_usage_maps_tokens(self):
        def fake_post(url, **kwargs):
            return self._mock_http_response(
                self._conv_response(
                    [self._message_output('ok')],
                    usage={
                        'prompt_tokens': 11,
                        'completion_tokens': 7,
                        'total_tokens': 18,
                    },
                )
            )

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            result = self.provider._request_responses(inputs=[])
        self.assertEqual(result['usage']['input_tokens'], 11)
        self.assertEqual(result['usage']['output_tokens'], 7)

    def test_token_cap_hit_appends_truncation_notice(self):
        def fake_post(url, **kwargs):
            return self._mock_http_response(
                self._conv_response(
                    [self._message_output('partial')],
                    usage={
                        'prompt_tokens': 11,
                        'completion_tokens': 4096,
                        'total_tokens': 4107,
                    },
                )
            )

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            result = self.provider._request_responses(inputs=[])
        self.assertIn('partial', result['text'])
        self.assertIn('Max Tokens', result['text'])
        self.assertEqual(result['usage']['output_tokens'], 4096)

    def test_token_cap_hit_without_text_still_yields_notice(self):
        def fake_post(url, **kwargs):
            return self._mock_http_response(
                self._conv_response(
                    [],
                    usage={
                        'prompt_tokens': 11,
                        'completion_tokens': 4096,
                        'total_tokens': 4107,
                    },
                )
            )

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            result = self.provider._request_responses(inputs=[])
        self.assertIn('Max Tokens', result['text'])
        self.assertEqual(result['usage']['output_tokens'], 4096)

    # ----------------------------------------------------------
    # Connectors
    # ----------------------------------------------------------

    def test_web_search_tool_injected_and_reference_rendered(self):
        captured = {}

        def fake_post(url, **kwargs):
            captured['body'] = kwargs.get('json')
            return self._mock_http_response(
                self._conv_response(
                    [
                        self._message_output(
                            [
                                {'type': 'text', 'text': 'Spain won'},
                                {
                                    'type': 'tool_reference',
                                    'tool': 'web_search',
                                    'title': 'Euro winners',
                                    'url': 'https://marca.com',
                                    'source': 'brave',
                                },
                                {'type': 'text', 'text': '.'},
                            ]
                        ),
                    ]
                )
            )

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            result = self.provider._request_responses(inputs=[], enable_web_search=True)
        self.assertIn({'type': 'web_search'}, captured['body']['tools'])
        self.assertIn('Spain won', result['text'])
        self.assertIn('[Euro winners](https://marca.com)', result['text'])

    def test_code_interpreter_tool_injected_and_output_rendered(self):
        captured = {}

        def fake_post(url, **kwargs):
            captured['body'] = kwargs.get('json')
            return self._mock_http_response(
                self._conv_response(
                    [
                        {
                            'type': 'tool.execution',
                            'name': 'code_interpreter',
                            'info': {'code': 'print(1)', 'code_output': '1\n'},
                        },
                        self._message_output('done'),
                    ]
                )
            )

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            result = self.provider._request_responses(
                inputs=[], enable_code_interpreter=True
            )
        self.assertIn({'type': 'code_interpreter'}, captured['body']['tools'])
        self.assertIn('```python', result['text'])
        self.assertIn('print(1)', result['text'])
        self.assertIn('done', result['text'])

    def test_generate_image_drives_the_connector_in_one_shot(self):
        captured = {}

        def fake_post(url, **kwargs):
            captured.update(url=url, body=kwargs.get('json'))
            return self._mock_http_response(
                self._conv_response(
                    [
                        {
                            'object': 'entry',
                            'type': 'tool.execution',
                            'name': 'image_generation',
                        },
                        self._message_output(
                            [
                                {
                                    'type': 'tool_file',
                                    'tool': 'image_generation',
                                    'file_id': 'file_1',
                                    'file_name': 'image_generated_0',
                                    'file_type': 'png',
                                },
                            ]
                        ),
                    ]
                )
            )

        def fake_get(url, **kwargs):
            captured['file_url'] = url
            return self._mock_http_response(content=b'\xff\xd8\xff\xe0JFIF')

        with (
            patch.object(requests.Session, 'post', side_effect=fake_post),
            patch.object(requests.Session, 'get', side_effect=fake_get),
        ):
            result = self.provider._get_client().generate_image(
                'mistral-medium-latest', 'a cat', {'size': '1024x1024'}
            )
        self.assertTrue(captured['url'].endswith('/conversations'))
        self.assertEqual(captured['body']['model'], 'mistral-medium-latest')
        self.assertEqual(captured['body']['tools'], [{'type': 'image_generation'}])
        self.assertFalse(captured['body']['store'])
        self.assertIn('exactly once', captured['body']['instructions'])
        self.assertEqual(captured['body']['inputs'][0]['content'], 'a cat')
        self.assertNotIn('size', json.dumps(captured['body']))
        self.assertTrue(captured['file_url'].endswith('/files/file_1/content'))
        self.assertEqual(result['mimetype'], 'image/jpeg')
        self.assertEqual(
            result['data_b64'], base64.b64encode(b'\xff\xd8\xff\xe0JFIF').decode()
        )
        self.assertEqual(result['usage'], {'images': 1})

    def test_generate_image_runs_on_the_image_timeout(self):
        self.provider.write({'request_timeout': 15, 'image_timeout': 240})
        captured = {}

        def fake_post(url, **kwargs):
            captured.update(kwargs)
            return self._mock_http_response(
                self._conv_response(
                    [
                        self._message_output(
                            [
                                {
                                    'type': 'tool_file',
                                    'tool': 'image_generation',
                                    'file_id': 'file_1',
                                }
                            ]
                        )
                    ]
                )
            )

        with (
            patch.object(requests.Session, 'post', side_effect=fake_post),
            patch.object(
                requests.Session,
                'get',
                return_value=self._mock_http_response(content=b'fake-png'),
            ),
        ):
            self.provider._get_client().generate_image('mistral-medium-latest', 'a cat')
        self.assertEqual(captured['timeout'], 240)

    def test_generate_image_reports_a_driver_that_answered_with_text(self):
        response = self._mock_http_response(self._text_response('I cannot draw.'))
        with (
            patch.object(requests.Session, 'post', return_value=response),
            self.assertRaises(UserError) as caught,
        ):
            self.provider._get_client().generate_image('mistral-medium-latest', 'x')
        self.assertIn('answered with text', str(caught.exception))

    def test_generate_image_reports_a_failed_download(self):
        response = self._mock_http_response(
            self._conv_response(
                [
                    self._message_output(
                        [
                            {
                                'type': 'tool_file',
                                'tool': 'image_generation',
                                'file_id': 'f',
                            }
                        ]
                    )
                ]
            )
        )
        with (
            patch.object(requests.Session, 'post', return_value=response),
            patch.object(
                requests.Session, 'get', side_effect=requests.ConnectionError('boom')
            ),
            self.assertRaises(UserError) as caught,
        ):
            self.provider._get_client().generate_image('mistral-medium-latest', 'x')
        self.assertIn('boom', str(caught.exception))

    def test_tool_file_download_failure_falls_back_to_text(self):
        def fake_post(url, **kwargs):
            return self._mock_http_response(
                self._conv_response(
                    [
                        self._message_output(
                            [
                                {
                                    'type': 'tool_file',
                                    'tool': 'code_interpreter',
                                    'file_id': 'file_1',
                                    'file_name': 'plot',
                                    'file_type': 'png',
                                },
                            ]
                        ),
                    ]
                )
            )

        def fake_get(url, **kwargs):
            msg = 'boom'
            raise requests.ConnectionError(msg)

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            with patch.object(requests.Session, 'get', side_effect=fake_get):
                result = self.provider._request_responses(
                    inputs=[],
                    enable_code_interpreter=True,
                )
        self.assertIn('generated file', result['text'])

    # ----------------------------------------------------------
    # Attachments
    # ----------------------------------------------------------

    def test_attachment_image_becomes_image_url(self):
        captured = {}

        def fake_post(url, **kwargs):
            captured['body'] = kwargs.get('json')
            return self._mock_http_response(self._text_response('ok'))

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
        content = captured['body']['inputs'][0]['content']
        self.assertEqual(content[0]['type'], 'image_url')
        self.assertEqual(content[0]['image_url'], 'data:image/png;base64,AAA=')

    def test_attachment_pdf_becomes_document_part(self):
        captured = {}

        def fake_post(url, **kwargs):
            captured['body'] = kwargs.get('json')
            return self._mock_http_response(self._text_response('ok'))

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            self.provider._request_responses(
                inputs=[
                    {
                        'role': 'user',
                        'content': [
                            {'type': 'input_text', 'text': 'Summarize this'},
                            {
                                'type': 'muk_ai_attachment',
                                'strategy': 'file',
                                'mimetype': 'application/pdf',
                                'data_b64': 'AAA=',
                                'filename': 'invoice.pdf',
                            },
                        ],
                    }
                ],
            )
        content = captured['body']['inputs'][0]['content']
        parts = content if isinstance(content, list) else [content]
        doc_parts = [
            part
            for part in parts
            if isinstance(part, dict) and part.get('type') == 'document_url'
        ]
        self.assertTrue(doc_parts)
        self.assertEqual(
            doc_parts[0]['document_url'], 'data:application/pdf;base64,AAA='
        )
        text_parts = [
            part
            for part in parts
            if isinstance(part, dict) and part.get('type') == 'text'
        ]
        self.assertTrue(text_parts)
        self.assertIn('Summarize this', text_parts[0]['text'])

    def test_attachment_text_becomes_text_with_filename_prefix(self):
        captured = {}

        def fake_post(url, **kwargs):
            captured['body'] = kwargs.get('json')
            return self._mock_http_response(self._text_response('ok'))

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
        content = captured['body']['inputs'][0]['content']
        self.assertIn('--- File: note.txt (text/plain) ---', content)
        self.assertIn('hello\nworld', content)
        self.assertIn('[truncated]', content)

    # ----------------------------------------------------------
    # Streaming
    # ----------------------------------------------------------

    def test_stream_emits_text_and_function_deltas(self):
        sse = self._sse_lines(
            [
                {'type': 'conversation.response.started', 'conversation_id': 'conv_1'},
                {'type': 'message.output.delta', 'output_index': 0, 'content': 'Hel'},
                {'type': 'message.output.delta', 'output_index': 0, 'content': 'lo'},
                {
                    'type': 'function.call.delta',
                    'output_index': 1,
                    'tool_call_id': 'c1',
                    'name': 'do_x',
                    'arguments': '{"a":',
                },
                {'type': 'function.call.delta', 'output_index': 1, 'arguments': ' 1}'},
                {
                    'type': 'conversation.response.done',
                    'usage': {
                        'prompt_tokens': 7,
                        'completion_tokens': 4,
                        'total_tokens': 11,
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
        text_deltas = [p['delta'] for (k, p) in deltas if k == 'text']
        tool_starts = [p for (k, p) in deltas if k == 'tool_start']
        self.assertEqual(text_deltas, ['Hel', 'lo'])
        self.assertEqual(tool_starts[0]['name'], 'do_x')
        self.assertEqual(result['text'], 'Hello')
        self.assertEqual(len(result['tool_calls']), 1)
        self.assertEqual(result['tool_calls'][0]['arguments'], {'a': 1})
        self.assertEqual(result['tool_calls'][0]['call_id'], 'c1')
        self.assertEqual(result['usage']['input_tokens'], 7)
        self.assertEqual(result['usage']['output_tokens'], 4)

    def test_stream_emits_reasoning_deltas(self):
        sse = self._sse_lines(
            [
                {
                    'type': 'message.output.delta',
                    'output_index': 0,
                    'content': {
                        'type': 'thinking',
                        'thinking': [{'type': 'text', 'text': 'Let me '}],
                    },
                },
                {
                    'type': 'message.output.delta',
                    'output_index': 0,
                    'content': {
                        'type': 'thinking',
                        'thinking': [{'type': 'text', 'text': 'think.'}],
                    },
                },
                {
                    'type': 'message.output.delta',
                    'output_index': 0,
                    'content': 'Answer',
                },
                {
                    'type': 'conversation.response.done',
                    'usage': {'prompt_tokens': 5, 'completion_tokens': 3},
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
        reasoning = [p['delta'] for (k, p) in deltas if k == 'reasoning']
        text = [p['delta'] for (k, p) in deltas if k == 'text']
        self.assertEqual(reasoning, ['Let me ', 'think.'])
        self.assertEqual(text, ['Answer'])
        self.assertEqual(result['text'], 'Answer')

    def test_stream_token_cap_hit_appends_truncation_notice(self):
        sse = self._sse_lines(
            [
                {
                    'type': 'message.output.delta',
                    'output_index': 0,
                    'content': 'partial',
                },
                {
                    'type': 'conversation.response.done',
                    'usage': {
                        'prompt_tokens': 7,
                        'completion_tokens': 4096,
                        'total_tokens': 4103,
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

    def test_streaming_failure_falls_back_to_non_stream(self):
        calls = {'stream': 0, 'plain': 0}

        def fake_post(url, **kwargs):
            body = kwargs.get('json') or {}
            if body.get('stream'):
                calls['stream'] += 1
                resp = self._mock_http_response({}, status_code=500)
                resp.text = ''
                resp.raise_for_status.side_effect = requests.HTTPError(
                    '500', response=resp
                )
                return resp
            calls['plain'] += 1
            return self._mock_http_response(self._text_response('fallback answer'))

        deltas = []
        with patch.object(requests.Session, 'post', side_effect=fake_post):
            result = self.provider._request_responses(
                inputs=[],
                on_delta=lambda k, p: deltas.append((k, p)),
            )
        self.assertEqual(calls['stream'], STREAM_ATTEMPTS)
        self.assertEqual(calls['plain'], 1)
        self.assertEqual(result['text'], 'fallback answer')
        self.assertIn(
            'fallback answer', [p.get('delta') for (k, p) in deltas if k == 'text']
        )

    def test_connector_request_streams(self):
        sse = self._sse_lines(
            [
                {'type': 'message.output.delta', 'output_index': 0, 'content': 'web '},
                {
                    'type': 'message.output.delta',
                    'output_index': 0,
                    'content': 'answer',
                },
                {
                    'type': 'conversation.response.done',
                    'usage': {'prompt_tokens': 5, 'completion_tokens': 2},
                },
            ]
        )
        response = MagicMock()
        response.iter_lines.return_value = iter(sse)
        response.raise_for_status.return_value = None
        posts = []

        def fake_post(url, **kwargs):
            posts.append(kwargs.get('json') or {})
            return response

        deltas = []
        with patch.object(requests.Session, 'post', side_effect=fake_post):
            result = self.provider._request_responses(
                inputs=[],
                enable_web_search=True,
                on_delta=lambda k, p: deltas.append((k, p)),
            )
        self.assertEqual(len(posts), 1)
        self.assertTrue(posts[0].get('stream'))
        self.assertIn({'type': 'web_search'}, posts[0]['tools'])
        self.assertEqual(result['text'], 'web answer')
        self.assertEqual(
            [p['delta'] for (k, p) in deltas if k == 'text'],
            ['web ', 'answer'],
        )

    def test_buffered_request_retries_transient_server_error(self):
        seq = [500, 200]

        def fake_post(url, **kwargs):
            code = seq.pop(0) if seq else 200
            if code == 500:
                resp = self._mock_http_response({}, status_code=500)
                resp.text = ''
                resp.raise_for_status.side_effect = requests.HTTPError(
                    '500', response=resp
                )
                return resp
            return self._mock_http_response(self._text_response('ok'))

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            result = self.provider._request_responses(inputs=[], enable_web_search=True)
        self.assertEqual(result['text'], 'ok')
        self.assertEqual(seq, [])

    def test_stream_renders_code_execution(self):
        sse = self._sse_lines(
            [
                {
                    'type': 'tool.execution.done',
                    'name': 'code_interpreter',
                    'info': {'code': 'print(1)', 'code_output': '1\n'},
                },
                {'type': 'message.output.delta', 'output_index': 1, 'content': 'ok'},
                {'type': 'conversation.response.done', 'usage': {}},
            ]
        )
        response = MagicMock()
        response.iter_lines.return_value = iter(sse)
        response.raise_for_status.return_value = None

        with patch.object(requests.Session, 'post', return_value=response):
            result = self.provider._request_responses(
                inputs=[],
                on_delta=lambda k, p: None,
            )
        self.assertIn('```python', result['text'])
        self.assertIn('print(1)', result['text'])
        self.assertIn('ok', result['text'])

    # ----------------------------------------------------------
    # Connection / errors
    # ----------------------------------------------------------

    def test_test_connection_returns_true_on_text_response(self):
        def fake_post(url, **kwargs):
            return self._mock_http_response(self._text_response('ok'))

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            self.assertTrue(self.provider._get_client().test_connection())

    def test_request_raises_on_http_error(self):
        response = self._mock_http_response({}, status_code=400)
        response.text = 'invalid_request'
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

    def test_empty_outputs_returns_empty_text(self):
        def fake_post(url, **kwargs):
            return self._mock_http_response(self._conv_response([]))

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            result = self.provider._request_responses(inputs=[])
        self.assertEqual(result['text'], '')
        self.assertEqual(result['tool_calls'], [])

    def test_buffered_request_gives_up_after_every_attempt(self):
        attempts = []

        def fake_post(url, **kwargs):
            attempts.append(url)
            resp = self._mock_http_response({}, status_code=503)
            resp.text = 'upstream down'
            resp.raise_for_status.side_effect = requests.HTTPError('503', response=resp)
            return resp

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            with self.assertRaises(UserError) as capture:
                self.provider._request_responses(inputs=[])
        self.assertEqual(len(attempts), REQUEST_ATTEMPTS)
        self.assertIn('upstream down', str(capture.exception))

    def test_transport_failure_is_wrapped_in_a_user_error(self):
        with patch.object(
            requests.Session,
            'post',
            side_effect=requests.ConnectionError('name resolution failed'),
        ):
            with self.assertRaises(UserError) as capture:
                self.provider._request_responses(inputs=[])
        self.assertIn('name resolution failed', str(capture.exception))

    # ----------------------------------------------------------
    # Tool schema
    # ----------------------------------------------------------

    def test_tool_schema_dedupes_and_skips_unnamed_tools(self):
        tools = MistralProvider._tools_to_mistral(
            [
                {'name': 'alpha', 'description': 'first'},
                {'name': 'alpha', 'description': 'duplicate'},
                {'description': 'no name'},
                {'name': '', 'description': 'empty name'},
                {
                    'name': 'beta',
                    'parameters': {'type': 'object', 'properties': {'x': {}}},
                },
            ]
        )
        self.assertEqual(
            [tool['function']['name'] for tool in tools],
            ['alpha', 'beta'],
        )
        self.assertEqual(tools[0]['function']['description'], 'first')
        self.assertEqual(
            tools[0]['function']['parameters'],
            {'type': 'object', 'properties': {}},
        )
        self.assertIn('x', tools[1]['function']['parameters']['properties'])

    def test_no_tools_key_when_nothing_is_declared(self):
        captured = {}

        def fake_post(url, **kwargs):
            captured['body'] = kwargs.get('json')
            return self._mock_http_response(self._text_response('ok'))

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            self.provider._request_responses(inputs=[], tools_schema=[])
        self.assertNotIn('tools', captured['body'])

    # ----------------------------------------------------------
    # Protected tool names
    # ----------------------------------------------------------

    def test_protected_tool_names_travel_under_a_prefix(self):
        tools = MistralProvider._tools_to_mistral(
            [
                {'name': 'web_search'},
                {'name': 'generate_image'},
                {'name': 'search_read'},
                {'name': 'web_fetch'},
            ]
        )
        self.assertEqual(
            [tool['function']['name'] for tool in tools],
            [
                f'{TOOL_NAME_PREFIX}web_search',
                f'{TOOL_NAME_PREFIX}generate_image',
                'search_read',
                'web_fetch',
            ],
        )

    def test_a_protected_function_call_entry_uses_the_same_wire_name(self):
        _instructions, entries = MistralProvider._inputs_to_entries(
            [
                {
                    'type': 'function_call',
                    'name': 'web_search',
                    'arguments': '{"query": "odoo"}',
                    'call_id': 'c1',
                },
                {
                    'type': 'function_call',
                    'name': 'search_read',
                    'arguments': '{}',
                    'call_id': 'c2',
                },
            ]
        )
        self.assertEqual(entries[0]['name'], f'{TOOL_NAME_PREFIX}web_search')
        self.assertEqual(entries[1]['name'], 'search_read')

    def test_a_buffered_protected_call_maps_back_to_its_muk_ai_name(self):
        def fake_post(url, **kwargs):
            return self._mock_http_response(
                self._conv_response(
                    [
                        self._function_call(
                            'c1',
                            f'{TOOL_NAME_PREFIX}generate_image',
                            {'prompt': 'a red cube'},
                        ),
                    ]
                )
            )

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            result = self.provider._request_responses(inputs=[])
        self.assertEqual(result['tool_calls'][0]['name'], 'generate_image')
        self.assertEqual(result['carry_inputs'][0]['name'], 'generate_image')

    def test_a_streamed_protected_call_maps_back_to_its_muk_ai_name(self):
        sse = self._sse_lines(
            [
                {
                    'type': 'function.call.delta',
                    'output_index': 0,
                    'id': 'fc_1',
                    'name': f'{TOOL_NAME_PREFIX}web_search',
                    'tool_call_id': 'Y2T9LVzh8',
                    'arguments': '',
                },
                {
                    'type': 'function.call.delta',
                    'output_index': 0,
                    'id': 'fc_1',
                    'name': f'{TOOL_NAME_PREFIX}web_search',
                    'tool_call_id': 'Y2T9LVzh8',
                    'arguments': '{"query": "Mistral AI CEO"}',
                },
                {
                    'type': 'conversation.response.done',
                    'usage': {'prompt_tokens': 69, 'completion_tokens': 22},
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
        tool_starts = [payload for (kind, payload) in deltas if kind == 'tool_start']
        self.assertEqual(tool_starts[0]['name'], 'web_search')
        self.assertEqual(result['tool_calls'][0]['name'], 'web_search')
        self.assertEqual(
            result['tool_calls'][0]['arguments'],
            {'query': 'Mistral AI CEO'},
        )
        self.assertEqual(result['carry_inputs'][0]['name'], 'web_search')

    def test_a_streamed_control_call_keeps_its_name(self):
        sse = self._sse_lines(
            [
                {
                    'type': 'function.call.delta',
                    'output_index': 0,
                    'id': 'fc_1',
                    'name': 'search_read',
                    'tool_call_id': 'Y2T9LVzh8',
                    'arguments': '{"model": "res.partner"}',
                },
                {
                    'type': 'conversation.response.done',
                    'usage': {'prompt_tokens': 69, 'completion_tokens': 22},
                },
            ]
        )
        response = MagicMock()
        response.iter_lines.return_value = iter(sse)
        response.raise_for_status.return_value = None
        with patch.object(requests.Session, 'post', return_value=response):
            result = self.provider._request_responses(
                inputs=[],
                on_delta=lambda kind, payload: None,
            )
        self.assertEqual(result['tool_calls'][0]['name'], 'search_read')

    def test_a_native_connector_execution_is_not_read_as_a_function_call(self):
        sse = self._sse_lines(
            [
                {
                    'type': 'tool.execution.started',
                    'output_index': 0,
                    'id': 'tool_exec_1',
                    'name': 'image_generation',
                    'arguments': '{"',
                    'function': 'generate_image',
                },
                {
                    'type': 'tool.execution.delta',
                    'output_index': 0,
                    'id': 'tool_exec_1',
                    'name': 'image_generation',
                    'arguments': 'prompt": "a red cube"}',
                    'function': 'generate_image',
                },
                {
                    'type': 'tool.execution.done',
                    'output_index': 0,
                    'id': 'tool_exec_1',
                    'name': 'image_generation',
                    'function': 'generate_image',
                    'info': {'result': '{"url": "https://blob.example/image.jpg"}'},
                },
                {
                    'type': 'message.output.delta',
                    'output_index': 1,
                    'content': {
                        'type': 'tool_file',
                        'tool': 'image_generation',
                        'file_id': 'file_9',
                        'file_name': 'image_generated_0',
                        'file_type': 'png',
                    },
                },
                {
                    'type': 'conversation.response.done',
                    'usage': {'prompt_tokens': 200, 'completion_tokens': 316},
                },
            ]
        )
        response = MagicMock()
        response.iter_lines.return_value = iter(sse)
        response.raise_for_status.return_value = None

        def fake_get(url, **kwargs):
            return self._mock_http_response(content=b'\x89PNG\r\n\x1a\n')

        with (
            patch.object(requests.Session, 'post', return_value=response),
            patch.object(requests.Session, 'get', side_effect=fake_get),
        ):
            result = self.provider._request_responses(
                inputs=[],
                on_delta=lambda kind, payload: None,
            )
        self.assertEqual(result['tool_calls'], [])
        self.assertIn('data:image/png;base64,', result['text'])

    def test_a_native_web_search_execution_streams_its_references(self):
        sse = self._sse_lines(
            [
                {
                    'type': 'tool.execution.started',
                    'output_index': 0,
                    'id': 'tool_exec_1',
                    'name': 'web_search',
                    'arguments': '{"',
                    'function': 'web_search',
                },
                {
                    'type': 'tool.execution.done',
                    'output_index': 0,
                    'id': 'tool_exec_1',
                    'name': 'web_search',
                    'function': 'web_search',
                    'info': {'result': '{"YmzJrfbG": {"url": "https://mistral.ai/"}}'},
                },
                {
                    'type': 'message.output.delta',
                    'output_index': 1,
                    'content': 'Arthur Mensch',
                },
                {
                    'type': 'message.output.delta',
                    'output_index': 1,
                    'content': {
                        'type': 'tool_reference',
                        'tool': 'web_search',
                        'title': 'About Mistral',
                        'url': 'https://mistral.ai/about/',
                    },
                },
                {
                    'type': 'conversation.response.done',
                    'usage': {'prompt_tokens': 773, 'completion_tokens': 88},
                },
            ]
        )
        response = MagicMock()
        response.iter_lines.return_value = iter(sse)
        response.raise_for_status.return_value = None
        with patch.object(requests.Session, 'post', return_value=response):
            result = self.provider._request_responses(
                inputs=[],
                on_delta=lambda kind, payload: None,
            )
        self.assertEqual(result['tool_calls'], [])
        self.assertEqual(
            result['text'],
            'Arthur Mensch ([About Mistral](https://mistral.ai/about/))',
        )

    # ----------------------------------------------------------
    # Tool call parsing
    # ----------------------------------------------------------

    def test_malformed_tool_arguments_are_reported_not_raised(self):
        def fake_post(url, **kwargs):
            return self._mock_http_response(
                self._conv_response(
                    [
                        {
                            'object': 'entry',
                            'type': 'function.call',
                            'tool_call_id': 'c1',
                            'name': 'do_x',
                            'arguments': '{"a": ',
                        },
                    ]
                )
            )

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            result = self.provider._request_responses(inputs=[])
        call = result['tool_calls'][0]
        self.assertEqual(call['arguments'], {})
        self.assertIn('Malformed JSON arguments', call['_parse_error'])
        self.assertEqual(result['carry_inputs'][0]['arguments'], '{"a": ')

    def test_a_function_call_without_arguments_defaults_to_an_empty_object(self):
        def fake_post(url, **kwargs):
            return self._mock_http_response(
                self._conv_response(
                    [
                        {
                            'object': 'entry',
                            'type': 'function.call',
                            'id': 'fallback_id',
                            'name': 'do_x',
                        },
                    ]
                )
            )

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            result = self.provider._request_responses(inputs=[])
        call = result['tool_calls'][0]
        self.assertEqual(call['arguments'], {})
        self.assertEqual(call['call_id'], 'fallback_id')
        self.assertIsNone(call['_parse_error'])

    def test_assistant_text_carries_before_the_function_calls(self):
        def fake_post(url, **kwargs):
            return self._mock_http_response(
                self._conv_response(
                    [
                        self._message_output('Let me check.'),
                        self._function_call('c1', 'do_x', {}),
                    ]
                )
            )

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            result = self.provider._request_responses(inputs=[])
        self.assertEqual(result['carry_inputs'][0]['role'], 'assistant')
        self.assertEqual(
            result['carry_inputs'][0]['content'][0]['text'],
            'Let me check.',
        )
        self.assertEqual(result['carry_inputs'][1]['type'], 'function_call')

    def test_thinking_chunks_are_not_rendered_into_the_answer(self):
        def fake_post(url, **kwargs):
            return self._mock_http_response(
                self._conv_response(
                    [
                        self._message_output(
                            [
                                {
                                    'type': 'thinking',
                                    'thinking': [{'type': 'text', 'text': 'hmm'}],
                                },
                                {'type': 'text', 'text': 'Answer'},
                            ]
                        ),
                    ]
                )
            )

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            result = self.provider._request_responses(inputs=[])
        self.assertEqual(result['text'], 'Answer')

    def test_thinking_text_accepts_a_bare_string(self):
        self.assertEqual(
            MistralProvider._thinking_text({'thinking': 'plain'}),
            'plain',
        )
        self.assertEqual(MistralProvider._thinking_text({'thinking': 7}), '')

    def test_a_tool_execution_without_code_renders_nothing(self):
        self.assertEqual(MistralProvider._render_tool_execution({'info': {}}), '')
        self.assertEqual(MistralProvider._render_tool_execution({}), '')

    # ----------------------------------------------------------
    # Attachments
    # ----------------------------------------------------------

    def test_multiple_images_keep_the_text_part_first(self):
        content = MistralProvider._user_content_to_mistral(
            [
                {'type': 'input_text', 'text': 'compare these'},
                {
                    'type': 'muk_ai_attachment',
                    'strategy': 'image',
                    'mimetype': 'image/png',
                    'data_b64': 'AAA=',
                },
                {
                    'type': 'muk_ai_attachment',
                    'strategy': 'image',
                    'mimetype': 'image/jpeg',
                    'data_b64': 'BBB=',
                },
            ]
        )
        self.assertEqual(
            [part['type'] for part in content],
            ['text', 'image_url', 'image_url'],
        )
        self.assertEqual(content[0]['text'], 'compare these')

    def test_an_attachment_without_any_payload_is_dropped(self):
        self.assertIsNone(
            MistralProvider._attachment_to_part(
                {'strategy': 'image', 'filename': 'empty.png'},
            )
        )
        self.assertEqual(
            MistralProvider._user_content_to_mistral(
                [
                    {'type': 'muk_ai_attachment', 'strategy': 'file'},
                    {'type': 'input_text', 'text': 'still here'},
                ]
            ),
            'still here',
        )

    def test_empty_user_content_maps_to_an_empty_string(self):
        self.assertEqual(MistralProvider._user_content_to_mistral([]), '')
        self.assertEqual(MistralProvider._user_content_to_mistral(None), '')
        self.assertEqual(MistralProvider._user_content_to_mistral('plain'), 'plain')

    def test_a_string_system_message_is_taken_verbatim(self):
        instructions, entries = MistralProvider._inputs_to_entries(
            [
                {'role': 'system', 'content': 'be terse'},
                {'role': 'system', 'content': [{'type': 'input_text', 'text': 'and'}]},
            ]
        )
        self.assertEqual(instructions, 'be terse\n\nand')
        self.assertEqual(entries, [])

    # ----------------------------------------------------------
    # Streaming failures
    # ----------------------------------------------------------

    def test_a_stream_error_event_aborts_the_request(self):
        sse = self._sse_lines(
            [
                {
                    'type': 'conversation.response.error',
                    'error': {'message': 'context length exceeded'},
                },
            ]
        )

        def fake_post(url, **kwargs):
            response = MagicMock()
            response.iter_lines.return_value = iter(sse)
            response.raise_for_status.return_value = None
            if (kwargs.get('json') or {}).get('stream'):
                return response
            return self._mock_http_response(self._text_response('buffered'))

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            result = self.provider._request_responses(
                inputs=[],
                on_delta=lambda k, p: None,
            )
        self.assertEqual(
            result['text'],
            'buffered',
            'a stream that failed before emitting falls back to buffered',
        )

    def test_a_stream_that_fails_after_emitting_never_replays_the_output(self):
        sse = self._sse_lines(
            [
                {'type': 'message.output.delta', 'output_index': 0, 'content': 'Par'},
                {'type': 'error', 'message': 'upstream died'},
            ]
        )
        posts = []

        def fake_post(url, **kwargs):
            posts.append(kwargs.get('json') or {})
            response = MagicMock()
            response.iter_lines.return_value = iter(list(sse))
            response.raise_for_status.return_value = None
            return response

        deltas = []
        with patch.object(requests.Session, 'post', side_effect=fake_post):
            with self.assertRaises(UserError) as capture:
                self.provider._request_responses(
                    inputs=[],
                    on_delta=lambda k, p: deltas.append((k, p)),
                )
        self.assertIn('upstream died', str(capture.exception))
        self.assertEqual(len(posts), 1, 'no retry after visible output')
        self.assertEqual([p['delta'] for (k, p) in deltas if k == 'text'], ['Par'])

    def test_a_bare_string_stream_error_is_surfaced(self):
        sse = self._sse_lines([{'type': 'error', 'error': 'rate limited'}])

        def fake_post(url, **kwargs):
            if (kwargs.get('json') or {}).get('stream'):
                response = MagicMock()
                response.iter_lines.return_value = iter(list(sse))
                response.raise_for_status.return_value = None
                return response
            return self._mock_http_response(self._text_response('buffered'))

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            result = self.provider._request_responses(
                inputs=[],
                on_delta=lambda k, p: None,
            )
        self.assertEqual(result['text'], 'buffered')

    # ----------------------------------------------------------
    # Streaming shapes
    # ----------------------------------------------------------

    def test_a_complete_function_call_event_replaces_the_accumulated_arguments(self):
        sse = self._sse_lines(
            [
                {
                    'type': 'function.call.delta',
                    'output_index': 0,
                    'tool_call_id': 'c1',
                    'name': 'do_x',
                    'arguments': '{"partial"',
                },
                {
                    'type': 'function.call',
                    'output_index': 0,
                    'tool_call_id': 'c1',
                    'name': 'do_x',
                    'arguments': '{"a": 1}',
                },
                {'type': 'conversation.response.done', 'usage': {}},
            ]
        )
        response = MagicMock()
        response.iter_lines.return_value = iter(sse)
        response.raise_for_status.return_value = None
        with patch.object(requests.Session, 'post', return_value=response):
            result = self.provider._request_responses(
                inputs=[],
                on_delta=lambda k, p: None,
            )
        self.assertEqual(result['tool_calls'][0]['arguments'], {'a': 1})
        self.assertEqual(result['carry_inputs'][0]['call_id'], 'c1')

    def test_a_function_call_without_an_output_index_still_lands(self):
        sse = self._sse_lines(
            [
                {
                    'type': 'function.call',
                    'tool_call_id': 'c1',
                    'name': 'do_x',
                    'arguments': {'a': 1},
                },
                {'type': 'conversation.response.done', 'usage': {}},
            ]
        )
        response = MagicMock()
        response.iter_lines.return_value = iter(sse)
        response.raise_for_status.return_value = None
        with patch.object(requests.Session, 'post', return_value=response):
            result = self.provider._request_responses(
                inputs=[],
                on_delta=lambda k, p: None,
            )
        self.assertEqual(result['tool_calls'][0]['arguments'], {'a': 1})
        self.assertEqual(result['tool_calls'][0]['name'], 'do_x')

    def test_a_streamed_tool_reference_is_appended_to_the_text(self):
        sse = self._sse_lines(
            [
                {'type': 'message.output.delta', 'content': 'Spain won'},
                {
                    'type': 'message.output.delta',
                    'content': {
                        'type': 'tool_reference',
                        'title': 'Euro',
                        'url': 'https://marca.com',
                    },
                },
                {'type': 'conversation.response.done', 'usage': {}},
            ]
        )
        response = MagicMock()
        response.iter_lines.return_value = iter(sse)
        response.raise_for_status.return_value = None
        with patch.object(requests.Session, 'post', return_value=response):
            result = self.provider._request_responses(
                inputs=[],
                on_delta=lambda k, p: None,
            )
        self.assertIn('[Euro](https://marca.com)', result['text'])

    def test_a_streamed_generated_file_is_downloaded_after_the_stream(self):
        sse = self._sse_lines(
            [
                {'type': 'message.output.delta', 'content': 'Here it is:'},
                {
                    'type': 'message.output.delta',
                    'content': {
                        'type': 'tool_file',
                        'file_id': 'file_9',
                        'file_name': 'chart',
                        'file_type': 'png',
                    },
                },
                {'type': 'conversation.response.done', 'usage': {}},
            ]
        )
        response = MagicMock()
        response.iter_lines.return_value = iter(sse)
        response.raise_for_status.return_value = None
        captured = {}

        def fake_get(url, **kwargs):
            captured['url'] = url
            return self._mock_http_response(content=b'\x89PNG\r\n\x1a\n')

        deltas = []
        with (
            patch.object(requests.Session, 'post', return_value=response),
            patch.object(requests.Session, 'get', side_effect=fake_get),
        ):
            result = self.provider._request_responses(
                inputs=[],
                on_delta=lambda k, p: deltas.append((k, p)),
            )
        self.assertTrue(captured['url'].endswith('/files/file_9/content'))
        self.assertIn('data:image/png;base64,', result['text'])
        self.assertTrue(
            any('data:image/png' in p.get('delta', '') for (k, p) in deltas)
        )

    def test_a_tool_file_without_an_id_renders_nothing(self):
        self.assertEqual(self.provider._get_client()._render_tool_file({}), '')

    def test_stream_ignores_non_data_and_undecodable_lines(self):
        lines = [
            ': keepalive',
            'event: message',
            'data: not json',
            '',
            'data: [DONE]',
            '',
            'data: '
            + json.dumps(
                {'type': 'message.output.delta', 'content': 'ok'},
            ),
            '',
            'data: '
            + json.dumps(
                {'type': 'conversation.response.done', 'usage': {}},
            ),
            '',
        ]
        response = MagicMock()
        response.iter_lines.return_value = iter(lines)
        response.raise_for_status.return_value = None
        with patch.object(requests.Session, 'post', return_value=response):
            result = self.provider._request_responses(
                inputs=[],
                on_delta=lambda k, p: None,
            )
        self.assertEqual(result['text'], 'ok')
