import json
from unittest.mock import MagicMock, patch

import requests

from odoo.exceptions import UserError

from odoo.addons.muk_ai_mistral.providers.mistral import (
    STREAM_ATTEMPTS,
    MistralProvider,
)

from .common import MistralTestCommon


class TestAiMistralProvider(MistralTestCommon):

    # ----------------------------------------------------------
    # Inputs
    # ----------------------------------------------------------

    def test_inputs_to_entries_splits_system_and_maps_roles(self):
        instructions, entries = MistralProvider._inputs_to_entries([
            {'role': 'system', 'content': [{'type': 'input_text', 'text': 'be brief'}]},
            {'role': 'user', 'content': [{'type': 'input_text', 'text': 'hi'}]},
            {'type': 'function_call', 'name': 't', 'arguments': '{"a": 1}', 'call_id': 'c1'},
            {'type': 'function_call_output', 'call_id': 'c1', 'output': '"ok"'},
            {'role': 'assistant', 'content': [{'type': 'output_text', 'text': 'done'}]},
        ])
        self.assertEqual(instructions, 'be brief')
        self.assertEqual(entries[0], {
            'object': 'entry', 'type': 'message.input', 'role': 'user', 'content': 'hi',
        })
        self.assertEqual(entries[1]['type'], 'function.call')
        self.assertEqual(entries[1]['tool_call_id'], 'c1')
        self.assertEqual(entries[1]['name'], 't')
        self.assertEqual(entries[1]['arguments'], '{"a": 1}')
        self.assertEqual(entries[2], {
            'object': 'entry', 'type': 'function.result',
            'tool_call_id': 'c1', 'result': '"ok"',
        })
        self.assertEqual(entries[3], {
            'object': 'entry', 'type': 'message.output',
            'role': 'assistant', 'content': 'done',
        })

    def test_function_result_serialises_non_string_output(self):
        _instructions, entries = MistralProvider._inputs_to_entries([
            {'type': 'function_call_output', 'call_id': 'c1', 'output': {'ok': True}},
        ])
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

        with patch.object(requests, 'post', side_effect=fake_post):
            result = self.provider._request_responses(
                inputs=[
                    {'role': 'system', 'content': [{'type': 'input_text', 'text': 'be brief'}]},
                    {'role': 'user', 'content': [{'type': 'input_text', 'text': 'hi'}]},
                ],
                tools_schema=[{
                    'type': 'function', 'name': 'x', 'description': 'd',
                    'parameters': {'type': 'object', 'properties': {}},
                }],
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

        with patch.object(requests, 'post', side_effect=fake_post):
            self.provider._request_responses(inputs=[], model='mistral-large-latest')
        self.assertEqual(captured['body']['model'], 'mistral-large-latest')

    def test_request_omits_completion_args_when_no_max_tokens_or_schema(self):
        self.provider.max_tokens = 0
        captured = {}

        def fake_post(url, **kwargs):
            captured['body'] = kwargs.get('json')
            return self._mock_http_response(self._text_response('ok'))

        with patch.object(requests, 'post', side_effect=fake_post):
            self.provider._request_responses(inputs=[])
        self.assertNotIn('completion_args', captured['body'])

    def test_text_schema_sets_response_format(self):
        captured = {}

        def fake_post(url, **kwargs):
            captured['body'] = kwargs.get('json')
            return self._mock_http_response(self._text_response('ok'))

        with patch.object(requests, 'post', side_effect=fake_post):
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
            return self._mock_http_response(self._conv_response([
                self._function_call('6TI17yZkV', 'list_modules', {'installed_only': True}),
            ]))

        with patch.object(requests, 'post', side_effect=fake_post):
            result = self.provider._request_responses(inputs=[])
        self.assertEqual(len(result['tool_calls']), 1)
        self.assertEqual(result['tool_calls'][0]['name'], 'list_modules')
        self.assertEqual(result['tool_calls'][0]['arguments'], {'installed_only': True})
        self.assertEqual(result['tool_calls'][0]['call_id'], '6TI17yZkV')
        self.assertEqual(result['carry_inputs'][0]['type'], 'function_call')
        self.assertEqual(result['carry_inputs'][0]['call_id'], '6TI17yZkV')

    def test_usage_maps_tokens(self):
        def fake_post(url, **kwargs):
            return self._mock_http_response(self._conv_response(
                [self._message_output('ok')],
                usage={'prompt_tokens': 11, 'completion_tokens': 7, 'total_tokens': 18},
            ))

        with patch.object(requests, 'post', side_effect=fake_post):
            result = self.provider._request_responses(inputs=[])
        self.assertEqual(result['usage']['input_tokens'], 11)
        self.assertEqual(result['usage']['output_tokens'], 7)

    # ----------------------------------------------------------
    # Connectors
    # ----------------------------------------------------------

    def test_web_search_tool_injected_and_reference_rendered(self):
        captured = {}

        def fake_post(url, **kwargs):
            captured['body'] = kwargs.get('json')
            return self._mock_http_response(self._conv_response([
                self._message_output([
                    {'type': 'text', 'text': 'Spain won'},
                    {'type': 'tool_reference', 'tool': 'web_search',
                     'title': 'Euro winners', 'url': 'https://marca.com', 'source': 'brave'},
                    {'type': 'text', 'text': '.'},
                ]),
            ]))

        with patch.object(requests, 'post', side_effect=fake_post):
            result = self.provider._request_responses(inputs=[], enable_web_search=True)
        self.assertIn({'type': 'web_search'}, captured['body']['tools'])
        self.assertIn('Spain won', result['text'])
        self.assertIn('[Euro winners](https://marca.com)', result['text'])

    def test_code_interpreter_tool_injected_and_output_rendered(self):
        captured = {}

        def fake_post(url, **kwargs):
            captured['body'] = kwargs.get('json')
            return self._mock_http_response(self._conv_response([
                {'type': 'tool.execution', 'name': 'code_interpreter',
                 'info': {'code': 'print(1)', 'code_output': '1\n'}},
                self._message_output('done'),
            ]))

        with patch.object(requests, 'post', side_effect=fake_post):
            result = self.provider._request_responses(inputs=[], enable_code_interpreter=True)
        self.assertIn({'type': 'code_interpreter'}, captured['body']['tools'])
        self.assertIn('```python', result['text'])
        self.assertIn('print(1)', result['text'])
        self.assertIn('done', result['text'])

    def test_image_generation_tool_injected_and_file_downloaded(self):
        captured = {}

        def fake_post(url, **kwargs):
            captured['body'] = kwargs.get('json')
            return self._mock_http_response(self._conv_response([
                self._message_output([
                    {'type': 'tool_file', 'tool': 'image_generation',
                     'file_id': 'file_1', 'file_name': 'cat', 'file_type': 'png'},
                ]),
            ]))

        def fake_get(url, **kwargs):
            captured['file_url'] = url
            return self._mock_http_response(content=b'\x89PNG')

        with patch.object(requests, 'post', side_effect=fake_post):
            with patch.object(requests, 'get', side_effect=fake_get):
                result = self.provider._request_responses(
                    inputs=[], enable_image_generation=True,
                )
        self.assertIn({'type': 'image_generation'}, captured['body']['tools'])
        self.assertTrue(captured['file_url'].endswith('/files/file_1/content'))
        self.assertIn('data:image/png;base64,', result['text'])

    def test_image_file_download_failure_falls_back_to_text(self):
        def fake_post(url, **kwargs):
            return self._mock_http_response(self._conv_response([
                self._message_output([
                    {'type': 'tool_file', 'tool': 'image_generation',
                     'file_id': 'file_1', 'file_name': 'cat', 'file_type': 'png'},
                ]),
            ]))

        def fake_get(url, **kwargs):
            raise requests.ConnectionError('boom')

        with patch.object(requests, 'post', side_effect=fake_post):
            with patch.object(requests, 'get', side_effect=fake_get):
                result = self.provider._request_responses(
                    inputs=[], enable_image_generation=True,
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

        with patch.object(requests, 'post', side_effect=fake_post):
            self.provider._request_responses(
                inputs=[{'role': 'user', 'content': [{
                    'type': 'muk_ai_attachment',
                    'strategy': 'image',
                    'mimetype': 'image/png',
                    'data_b64': 'AAA=',
                    'filename': 'p.png',
                }]}],
            )
        content = captured['body']['inputs'][0]['content']
        self.assertEqual(content[0]['type'], 'image_url')
        self.assertEqual(content[0]['image_url'], 'data:image/png;base64,AAA=')

    def test_attachment_text_becomes_text_with_filename_prefix(self):
        captured = {}

        def fake_post(url, **kwargs):
            captured['body'] = kwargs.get('json')
            return self._mock_http_response(self._text_response('ok'))

        with patch.object(requests, 'post', side_effect=fake_post):
            self.provider._request_responses(
                inputs=[{'role': 'user', 'content': [{
                    'type': 'muk_ai_attachment',
                    'strategy': 'inline',
                    'mimetype': 'text/plain',
                    'inline_text': 'hello\nworld',
                    'filename': 'note.txt',
                    'truncated': True,
                }]}],
            )
        content = captured['body']['inputs'][0]['content']
        self.assertIn('--- File: note.txt (text/plain) ---', content)
        self.assertIn('hello\nworld', content)
        self.assertIn('[truncated]', content)

    # ----------------------------------------------------------
    # Streaming
    # ----------------------------------------------------------

    def test_stream_emits_text_and_function_deltas(self):
        sse = self._sse_lines([
            {'type': 'conversation.response.started', 'conversation_id': 'conv_1'},
            {'type': 'message.output.delta', 'output_index': 0, 'content': 'Hel'},
            {'type': 'message.output.delta', 'output_index': 0, 'content': 'lo'},
            {'type': 'function.call.delta', 'output_index': 1,
             'tool_call_id': 'c1', 'name': 'do_x', 'arguments': '{"a":'},
            {'type': 'function.call.delta', 'output_index': 1, 'arguments': ' 1}'},
            {'type': 'conversation.response.done',
             'usage': {'prompt_tokens': 7, 'completion_tokens': 4, 'total_tokens': 11}},
        ])
        response = MagicMock()
        response.iter_lines.return_value = iter(sse)
        response.raise_for_status.return_value = None

        deltas = []

        with patch.object(requests, 'post', return_value=response):
            result = self.provider._request_responses(
                inputs=[], on_delta=lambda k, p: deltas.append((k, p)),
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

    def test_streaming_failure_falls_back_to_non_stream(self):
        calls = {'stream': 0, 'plain': 0}

        def fake_post(url, **kwargs):
            body = kwargs.get('json') or {}
            if body.get('stream'):
                calls['stream'] += 1
                resp = self._mock_http_response({}, status_code=500)
                resp.text = ''
                resp.raise_for_status.side_effect = requests.HTTPError('500', response=resp)
                return resp
            calls['plain'] += 1
            return self._mock_http_response(self._text_response('fallback answer'))

        deltas = []
        with patch.object(requests, 'post', side_effect=fake_post):
            result = self.provider._request_responses(
                inputs=[], on_delta=lambda k, p: deltas.append((k, p)),
            )
        self.assertEqual(calls['stream'], STREAM_ATTEMPTS)
        self.assertEqual(calls['plain'], 1)
        self.assertEqual(result['text'], 'fallback answer')
        self.assertIn('fallback answer', [p.get('delta') for (k, p) in deltas if k == 'text'])

    def test_stream_renders_code_execution(self):
        sse = self._sse_lines([
            {'type': 'tool.execution.done', 'name': 'code_interpreter',
             'info': {'code': 'print(1)', 'code_output': '1\n'}},
            {'type': 'message.output.delta', 'output_index': 1, 'content': 'ok'},
            {'type': 'conversation.response.done', 'usage': {}},
        ])
        response = MagicMock()
        response.iter_lines.return_value = iter(sse)
        response.raise_for_status.return_value = None

        with patch.object(requests, 'post', return_value=response):
            result = self.provider._request_responses(
                inputs=[], on_delta=lambda k, p: None,
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

        with patch.object(requests, 'post', side_effect=fake_post):
            self.assertTrue(self.provider._get_client().test_connection())

    def test_request_raises_on_http_error(self):
        response = self._mock_http_response({}, status_code=400)
        response.text = 'invalid_request'
        response.raise_for_status.side_effect = requests.HTTPError('400', response=response)
        with patch.object(requests, 'post', return_value=response):
            with self.assertRaises(UserError):
                self.provider._request_responses(inputs=[])

    def test_request_raises_on_missing_key(self):
        self.provider.sudo().api_key = ''
        with self.assertRaises(UserError):
            self.provider._request_responses(inputs=[])

    def test_empty_outputs_returns_empty_text(self):
        def fake_post(url, **kwargs):
            return self._mock_http_response(self._conv_response([]))

        with patch.object(requests, 'post', side_effect=fake_post):
            result = self.provider._request_responses(inputs=[])
        self.assertEqual(result['text'], '')
        self.assertEqual(result['tool_calls'], [])
