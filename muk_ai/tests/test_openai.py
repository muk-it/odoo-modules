from unittest.mock import patch

import requests

from odoo.exceptions import UserError

from odoo.addons.muk_ai.tools import build_tool_call_output

from .common import AITestCommon


class TestAiOpenAIProvider(AITestCommon):

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_request_responses_posts_to_responses_endpoint(self):
        captured = {}

        def fake_post(url, **kwargs):
            captured['url'] = url
            captured['body'] = kwargs.get('json')
            return self._mock_http_response({
                'output': [{
                    'type': 'message',
                    'content': [{'text': 'ok'}],
                }],
                'usage': {'input_tokens': 5, 'output_tokens': 2},
            })

        with patch.object(requests, 'post', side_effect=fake_post):
            result = self.provider._request_responses(
                inputs=[{'role': 'user', 'content': [{'type': 'input_text', 'text': 'hi'}]}],
            )
        self.assertTrue(captured['url'].endswith('/responses'))
        self.assertEqual(result['text'], 'ok')
        self.assertEqual(result['tool_calls'], [])
        self.assertEqual(result['usage']['input_tokens'], 5)

    def test_request_responses_parses_tool_calls(self):
        response = self._mock_http_response({
            'output': [{
                'type': 'function_call',
                'name': 'list_modules',
                'arguments': '{"installed_only": true}',
                'call_id': 'call_1',
            }],
            'usage': {},
        })
        with patch.object(requests, 'post', return_value=response):
            result = self.provider._request_responses(inputs=[])
        self.assertEqual(len(result['tool_calls']), 1)
        self.assertEqual(result['tool_calls'][0]['name'], 'list_modules')
        self.assertEqual(result['tool_calls'][0]['arguments'], {'installed_only': True})
        self.assertEqual(result['carry_inputs'][0]['type'], 'function_call')

    def test_request_responses_sends_tools_schema(self):
        captured = {}

        def fake_post(url, **kwargs):
            captured['body'] = kwargs.get('json')
            return self._mock_http_response({'output': [], 'usage': {}})

        with patch.object(requests, 'post', side_effect=fake_post):
            self.provider._request_responses(
                inputs=[], tools_schema=[{'type': 'function', 'name': 'x', 'parameters': {}}],
            )
        self.assertIn('tools', captured['body'])
        self.assertTrue(captured['body']['parallel_tool_calls'])

    def test_request_responses_sends_text_schema(self):
        captured = {}

        def fake_post(url, **kwargs):
            captured['body'] = kwargs.get('json')
            return self._mock_http_response({'output': [], 'usage': {}})

        with patch.object(requests, 'post', side_effect=fake_post):
            self.provider._request_responses(
                inputs=[],
                text_schema={'name': 'plan', 'schema': {'type': 'object'}},
            )
        self.assertEqual(
            captured['body']['text']['format']['type'], 'json_schema'
        )

    def test_request_responses_raises_on_http_error(self):
        response = self._mock_http_response({}, status_code=500)
        response.text = 'server error'
        response.raise_for_status.side_effect = requests.HTTPError('boom', response=response)
        with patch.object(requests, 'post', return_value=response):
            with self.assertRaises(UserError):
                self.provider._request_responses(inputs=[])

    def test_request_responses_raises_on_missing_key(self):
        self.provider.sudo().api_key = ''
        with self.assertRaises(UserError):
            self.provider._request_responses(inputs=[])

    def test_build_tool_call_output_serializes_dict(self):
        payload = build_tool_call_output('call_99', {'ok': True})
        self.assertEqual(payload['type'], 'function_call_output')
        self.assertEqual(payload['call_id'], 'call_99')
        self.assertIn('"ok"', payload['output'])

    def test_test_connection_returns_true_on_text_response(self):
        response = self._mock_http_response({
            'output': [{'type': 'message', 'content': [{'text': 'ok'}]}],
            'usage': {},
        })
        with patch.object(requests, 'post', return_value=response):
            self.assertTrue(self.provider._get_client().test_connection())

    def test_test_connection_raises_on_empty_text(self):
        response = self._mock_http_response({'output': [], 'usage': {}})
        with patch.object(requests, 'post', return_value=response):
            with self.assertRaises(UserError):
                self.provider._get_client().test_connection()

    def test_request_responses_sends_max_output_tokens(self):
        self.provider.max_tokens = 2048
        captured = {}

        def fake_post(url, **kwargs):
            captured['body'] = kwargs.get('json')
            return self._mock_http_response({'output': [], 'usage': {}})

        with patch.object(requests, 'post', side_effect=fake_post):
            self.provider._request_responses(inputs=[])
        self.assertEqual(captured['body']['max_output_tokens'], 2048)

    def test_request_responses_omits_max_tokens_when_zero(self):
        self.provider.max_tokens = 0
        captured = {}

        def fake_post(url, **kwargs):
            captured['body'] = kwargs.get('json')
            return self._mock_http_response({'output': [], 'usage': {}})

        with patch.object(requests, 'post', side_effect=fake_post):
            self.provider._request_responses(inputs=[])
        self.assertNotIn('max_output_tokens', captured['body'])

    def test_request_responses_uses_model_kwarg(self):
        captured = {}

        def fake_post(url, **kwargs):
            captured['body'] = kwargs.get('json')
            return self._mock_http_response({'output': [], 'usage': {}})

        with patch.object(requests, 'post', side_effect=fake_post):
            self.provider._request_responses(inputs=[], model='gpt-4o')
        self.assertEqual(captured['body']['model'], 'gpt-4o')

    def test_openai_injects_web_search_tool(self):
        captured = {}

        def fake_post(url, **kwargs):
            captured['body'] = kwargs.get('json')
            return self._mock_http_response({'output': [], 'usage': {}})

        with patch.object(requests, 'post', side_effect=fake_post):
            self.provider._request_responses(
                inputs=[], enable_web_search=True,
            )
        types = [t.get('type') for t in captured['body'].get('tools') or []]
        self.assertIn('web_search', types)

    def test_openai_injects_image_generation_tool(self):
        captured = {}

        def fake_post(url, **kwargs):
            captured['body'] = kwargs.get('json')
            return self._mock_http_response({'output': [], 'usage': {}})

        with patch.object(requests, 'post', side_effect=fake_post):
            self.provider._request_responses(
                inputs=[], enable_image_generation=True,
            )
        types = [t.get('type') for t in captured['body'].get('tools') or []]
        self.assertIn('image_generation', types)

    def test_openai_injects_code_interpreter_tool(self):
        captured = {}

        def fake_post(url, **kwargs):
            captured['body'] = kwargs.get('json')
            return self._mock_http_response({'output': [], 'usage': {}})

        with patch.object(requests, 'post', side_effect=fake_post):
            self.provider._request_responses(
                inputs=[], enable_code_interpreter=True,
            )
        tools = captured['body'].get('tools') or []
        ci = next((t for t in tools if t.get('type') == 'code_interpreter'), None)
        self.assertIsNotNone(ci)
        self.assertEqual((ci.get('container') or {}).get('type'), 'auto')

    def test_openai_omits_tools_when_flags_off(self):
        captured = {}

        def fake_post(url, **kwargs):
            captured['body'] = kwargs.get('json')
            return self._mock_http_response({'output': [], 'usage': {}})

        with patch.object(requests, 'post', side_effect=fake_post):
            self.provider._request_responses(inputs=[])
        self.assertNotIn('tools', captured['body'])
