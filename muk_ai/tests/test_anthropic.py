from unittest.mock import MagicMock, patch

import requests

from odoo.addons.muk_ai.providers.anthropic import AnthropicProvider

from odoo.addons.muk_ai.tests.common import AITestCommon


class TestAiAnthropicProvider(AITestCommon):

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    def setUp(self):
        super().setUp()
        self.provider = self.provider_anthropic

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _anthropic_body(self, text='ok', tool_uses=()):
        content = []
        if text:
            content.append({'type': 'text', 'text': text})
        for call_id, name, input_ in tool_uses:
            content.append({
                'type': 'tool_use', 'id': call_id, 'name': name, 'input': input_,
            })
        return {
            'id': 'msg_1',
            'type': 'message',
            'role': 'assistant',
            'content': content,
            'stop_reason': 'end_turn' if not tool_uses else 'tool_use',
            'usage': {'input_tokens': 3, 'output_tokens': 2},
        }

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_inputs_to_anthropic_splits_system_and_merges_runs(self):
        system, messages = AnthropicProvider._inputs_to_messages([
            {'role': 'system', 'content': [{'type': 'input_text', 'text': 'sys1'}]},
            {'role': 'system', 'content': [{'type': 'input_text', 'text': 'sys2'}]},
            {'role': 'user', 'content': [{'type': 'input_text', 'text': 'hi'}]},
            {'type': 'function_call', 'name': 't', 'arguments': '{"a": 1}', 'call_id': 'c1'},
            {'type': 'function_call_output', 'call_id': 'c1', 'output': '"ok"'},
            {'role': 'user', 'content': [{'type': 'input_text', 'text': 'next'}]},
        ])
        self.assertIn('sys1', system)
        self.assertIn('sys2', system)
        self.assertEqual(messages[0]['role'], 'user')
        self.assertEqual(messages[0]['content'][0], {'type': 'text', 'text': 'hi'})
        self.assertEqual(messages[1]['role'], 'assistant')
        self.assertEqual(messages[1]['content'][0]['type'], 'tool_use')
        self.assertEqual(messages[1]['content'][0]['input'], {'a': 1})
        self.assertEqual(messages[2]['role'], 'user')
        self.assertEqual(messages[2]['content'][0]['type'], 'tool_result')
        self.assertEqual(messages[2]['content'][1], {'type': 'text', 'text': 'next'})

    def test_anthropic_request_sends_messages_shape(self):
        captured = {}

        def fake_post(url, **kwargs):
            captured['url'] = url
            captured['body'] = kwargs.get('json')
            captured['headers'] = kwargs.get('headers')
            return self._mock_http_response(self._anthropic_body('hello'))

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
        self.assertTrue(captured['url'].endswith('/messages'))
        self.assertEqual(captured['body']['system'], 'be brief')
        self.assertEqual(captured['body']['messages'][0]['role'], 'user')
        self.assertEqual(captured['body']['tools'][0]['name'], 'x')
        self.assertIn('max_tokens', captured['body'])
        self.assertEqual(captured['headers']['anthropic-version'], '2023-06-01')
        self.assertEqual(result['text'], 'hello')
        self.assertEqual(result['tool_calls'], [])

    def test_anthropic_request_parses_tool_use(self):
        def fake_post(url, **kwargs):
            return self._mock_http_response(self._anthropic_body(
                text='', tool_uses=[('toolu_1', 'list_modules', {'installed_only': True})],
            ))

        with patch.object(requests, 'post', side_effect=fake_post):
            result = self.provider._request_responses(inputs=[])
        self.assertEqual(len(result['tool_calls']), 1)
        self.assertEqual(result['tool_calls'][0]['name'], 'list_modules')
        self.assertEqual(result['tool_calls'][0]['arguments'], {'installed_only': True})
        self.assertEqual(result['carry_inputs'][0]['type'], 'function_call')

    def test_anthropic_stream_emits_text_and_tool_deltas(self):
        sse = [
            'data: {"type":"message_start","message":{"usage":{"input_tokens":7}}}',
            '',
            'data: {"type":"content_block_start","index":0,"content_block":{"type":"text","text":""}}',
            '',
            'data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"Hel"}}',
            '',
            'data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"lo"}}',
            '',
            'data: {"type":"content_block_stop","index":0}',
            '',
            'data: {"type":"content_block_start","index":1,"content_block":{"type":"tool_use","id":"toolu_1","name":"do_x","input":{}}}',
            '',
            'data: {"type":"content_block_delta","index":1,"delta":{"type":"input_json_delta","partial_json":"{\\"a\\":"}}',
            '',
            'data: {"type":"content_block_delta","index":1,"delta":{"type":"input_json_delta","partial_json":"1}"}}',
            '',
            'data: {"type":"content_block_stop","index":1}',
            '',
            'data: {"type":"message_delta","usage":{"output_tokens":4}}',
            '',
            'data: {"type":"message_stop"}',
            '',
        ]
        response = MagicMock()
        response.iter_lines.return_value = iter(sse)
        response.raise_for_status.return_value = None

        def fake_post(url, **kwargs):
            return response

        deltas = []

        def on_delta(kind, payload):
            deltas.append((kind, payload))

        with patch.object(requests, 'post', side_effect=fake_post):
            result = self.provider._request_responses(inputs=[], on_delta=on_delta)
        text_deltas = [p['delta'] for (k, p) in deltas if k == 'text']
        tool_starts = [p for (k, p) in deltas if k == 'tool_start']
        tool_args = [p for (k, p) in deltas if k == 'tool_args']
        self.assertEqual(text_deltas, ['Hel', 'lo'])
        self.assertEqual(tool_starts[0]['call_id'], 'toolu_1')
        self.assertEqual(tool_starts[0]['name'], 'do_x')
        self.assertEqual(''.join(p['delta'] for p in tool_args), '{"a":1}')
        self.assertEqual(result['text'], 'Hello')
        self.assertEqual(len(result['tool_calls']), 1)
        self.assertEqual(result['tool_calls'][0]['arguments'], {'a': 1})
        self.assertEqual(result['usage']['input_tokens'], 7)
        self.assertEqual(result['usage']['output_tokens'], 4)

    def test_anthropic_injects_web_search_tool(self):
        captured = {}

        def fake_post(url, **kwargs):
            captured['body'] = kwargs.get('json')
            return self._mock_http_response(self._anthropic_body('ok'))

        with patch.object(requests, 'post', side_effect=fake_post):
            self.provider._request_responses(
                inputs=[], enable_web_search=True,
            )
        tools = captured['body'].get('tools') or []
        types = [t.get('type') for t in tools]
        self.assertIn('web_search_20250305', types)

    def test_anthropic_injects_code_execution_tool(self):
        captured = {}

        def fake_post(url, **kwargs):
            captured['body'] = kwargs.get('json')
            return self._mock_http_response(self._anthropic_body('ok'))

        with patch.object(requests, 'post', side_effect=fake_post):
            self.provider._request_responses(
                inputs=[], enable_code_interpreter=True,
            )
        tools = captured['body'].get('tools') or []
        types = [t.get('type') for t in tools]
        self.assertIn('code_execution_20250825', types)

    def test_anthropic_ignores_image_generation_flag(self):
        captured = {}

        def fake_post(url, **kwargs):
            captured['body'] = kwargs.get('json')
            return self._mock_http_response(self._anthropic_body('ok'))

        with patch.object(requests, 'post', side_effect=fake_post):
            self.provider._request_responses(
                inputs=[], enable_image_generation=True,
            )
        self.assertNotIn('tools', captured['body'])

    def test_anthropic_connection_test_ok(self):
        def fake_post(url, **kwargs):
            return self._mock_http_response(self._anthropic_body('ok'))

        with patch.object(requests, 'post', side_effect=fake_post):
            self.assertTrue(self.provider._get_client().test_connection())
