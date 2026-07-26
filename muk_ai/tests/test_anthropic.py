from __future__ import annotations

import copy
from collections.abc import Sequence
from unittest.mock import MagicMock, patch

import requests

from odoo.exceptions import UserError
from odoo.tools import mute_logger

from odoo.addons.muk_ai.providers.anthropic import AnthropicProvider
from odoo.addons.muk_ai.tests.common import AITestCommon


class TestAiAnthropicProvider(AITestCommon):
    """Verify the Anthropic provider request building, parsing, and streaming."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    def setUp(self) -> None:
        super().setUp()
        self.provider = self.provider_anthropic

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _anthropic_body(
        self,
        text: str = 'ok',
        tool_uses: Sequence[tuple[str, str, dict]] = (),
    ) -> dict:
        """Build an Anthropic messages response body.

        :param tool_uses: ``(call id, tool name, input)`` triples emitted as
            ``tool_use`` blocks next to the text block.
        """
        content = []
        if text:
            content.append({'type': 'text', 'text': text})
        for call_id, name, input_ in tool_uses:
            content.append(
                {
                    'type': 'tool_use',
                    'id': call_id,
                    'name': name,
                    'input': input_,
                }
            )
        return {
            'id': 'msg_1',
            'type': 'message',
            'role': 'assistant',
            'content': content,
            'stop_reason': 'end_turn' if not tool_uses else 'tool_use',
            'usage': {'input_tokens': 3, 'output_tokens': 2},
        }

    def _capture_request_body(
        self, model: str, reasoning_effort: str | None = None
    ) -> dict:
        """Run a minimal request against ``model`` and return the wire body."""
        captured = {}

        def fake_post(url, **kwargs):
            captured['body'] = kwargs.get('json')
            return self._mock_http_response(self._anthropic_body('ok'))

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            self.provider._request_responses(
                inputs=[
                    {'role': 'user', 'content': [{'type': 'input_text', 'text': 'hi'}]}
                ],
                model=model,
                reasoning_effort=reasoning_effort,
            )
        return captured['body']

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_adaptive_thinking_uses_reasoning_effort(self):
        body = self._capture_request_body('claude-opus-4-8', 'low')
        self.assertEqual(body['thinking'], {'type': 'adaptive'})
        self.assertEqual(body['output_config'], {'effort': 'low'})

    def test_adaptive_thinking_defaults_to_medium(self):
        body = self._capture_request_body('claude-opus-4-8')
        self.assertEqual(body['output_config'], {'effort': 'medium'})

    def test_legacy_thinking_low_effort_disables_thinking(self):
        body = self._capture_request_body('claude-sonnet-4-6', 'low')
        self.assertNotIn('thinking', body)

    def test_legacy_thinking_budget_scales_with_effort(self):
        default = self._capture_request_body('claude-sonnet-4-6')
        self.assertEqual(default['thinking']['budget_tokens'], 1024)
        high = self._capture_request_body('claude-sonnet-4-6', 'high')
        self.assertEqual(high['thinking']['budget_tokens'], 4096)
        maximum = self._capture_request_body('claude-sonnet-4-6', 'max')
        self.assertEqual(maximum['thinking']['budget_tokens'], 16384)

    def test_adaptive_thinking_maps_minimal_to_low(self):
        body = self._capture_request_body('claude-opus-4-8', 'minimal')
        self.assertEqual(body['output_config'], {'effort': 'low'})

    def test_adaptive_thinking_passes_xhigh_natively(self):
        body = self._capture_request_body('claude-opus-4-8', 'xhigh')
        self.assertEqual(body['output_config'], {'effort': 'xhigh'})

    def test_fable_and_sonnet_5_use_adaptive_thinking(self):
        for model in ('claude-fable-5', 'claude-sonnet-5'):
            body = self._capture_request_body(model, 'low')
            self.assertEqual(body['thinking'], {'type': 'adaptive'})
            self.assertEqual(body['output_config'], {'effort': 'low'})

    @mute_logger('odoo.addons.muk_ai.providers.base')
    def test_rejected_effort_keeps_thinking(self):
        record = self.env.ref('muk_ai.model_claude_opus_4_8')
        bodies = []

        def fake_post(url, **kwargs):
            bodies.append(copy.deepcopy(kwargs.get('json')))
            if len(bodies) == 1:
                response = self._mock_http_response({}, status_code=400)
                response.text = "Unexpected value for 'output_config.effort'."
                response.raise_for_status.side_effect = requests.HTTPError(
                    'bad request', response=response
                )
                return response
            return self._mock_http_response(self._anthropic_body('ok'))

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            result = self.provider._request_responses(
                inputs=[
                    {'role': 'user', 'content': [{'type': 'input_text', 'text': 'hi'}]}
                ],
                model='claude-opus-4-8',
                reasoning_effort='low',
            )
        self.assertEqual(len(bodies), 2)
        self.assertEqual(bodies[0]['output_config'], {'effort': 'low'})
        self.assertIn('thinking', bodies[1])
        self.assertNotIn('output_config', bodies[1])
        self.assertEqual(result['text'], 'ok')
        self.assertIn('low', record.reasoning_efforts)

    def test_unresolved_rejection_raises_and_learns_nothing(self):
        record = self.env.ref('muk_ai.model_claude_opus_4_8')
        bodies = []

        def fake_post(url, **kwargs):
            bodies.append(copy.deepcopy(kwargs.get('json')))
            response = self._mock_http_response({}, status_code=400)
            response.text = 'This model does not support thinking.'
            response.raise_for_status.side_effect = requests.HTTPError(
                'bad request', response=response
            )
            return response

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            with self.assertRaises(UserError):
                self.provider._request_responses(
                    inputs=[
                        {
                            'role': 'user',
                            'content': [{'type': 'input_text', 'text': 'hi'}],
                        }
                    ],
                    model='claude-opus-4-8',
                    reasoning_effort='low',
                )
        self.assertEqual(len(bodies), 2)
        self.assertIn('thinking', bodies[1])
        self.assertNotIn('output_config', bodies[1])
        self.assertIn('low', record.reasoning_efforts)

    def test_inputs_to_anthropic_splits_system_and_merges_runs(self):
        system, messages, _anchor = AnthropicProvider._inputs_to_messages(
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
        self.assertTrue(captured['url'].endswith('/messages'))
        self.assertEqual(
            captured['body']['system'],
            [
                {
                    'type': 'text',
                    'text': 'be brief',
                    'cache_control': {'type': 'ephemeral'},
                }
            ],
        )
        self.assertEqual(captured['body']['messages'][0]['role'], 'user')
        self.assertEqual(captured['body']['tools'][0]['name'], 'x')
        self.assertEqual(
            captured['body']['tools'][-1]['cache_control'], {'type': 'ephemeral'}
        )
        self.assertIn('max_tokens', captured['body'])
        self.assertEqual(captured['headers']['anthropic-version'], '2023-06-01')
        self.assertEqual(result['text'], 'hello')
        self.assertEqual(result['tool_calls'], [])

    def test_anthropic_request_parses_tool_use(self):
        def fake_post(url, **kwargs):
            return self._mock_http_response(
                self._anthropic_body(
                    text='',
                    tool_uses=[('toolu_1', 'list_modules', {'installed_only': True})],
                )
            )

        with patch.object(requests.Session, 'post', side_effect=fake_post):
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

        with patch.object(requests.Session, 'post', side_effect=fake_post):
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

    def test_anthropic_max_tokens_stop_appends_truncation_notice(self):
        body = self._anthropic_body('partial answer')
        body['stop_reason'] = 'max_tokens'
        with patch.object(
            requests.Session, 'post', return_value=self._mock_http_response(body)
        ):
            result = self.provider._request_responses(inputs=[])
        self.assertIn('partial answer', result['text'])
        self.assertIn('Max Tokens', result['text'])
        self.assertEqual(result['usage']['output_tokens'], 2)

    def test_anthropic_stream_max_tokens_stop_appends_truncation_notice(self):
        sse = [
            'data: {"type":"message_start","message":{"usage":{"input_tokens":7}}}',
            '',
            'data: {"type":"content_block_start","index":0,"content_block":{"type":"text","text":""}}',
            '',
            'data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"partial"}}',
            '',
            'data: {"type":"message_delta","delta":{"stop_reason":"max_tokens"},"usage":{"output_tokens":4096}}',
            '',
            'data: {"type":"message_stop"}',
            '',
        ]
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
        self.assertEqual(result['usage']['input_tokens'], 7)
        self.assertEqual(result['usage']['output_tokens'], 4096)
        text_deltas = [p['delta'] for (k, p) in deltas if k == 'text']
        self.assertTrue(any('Max Tokens' in d for d in text_deltas))

    def test_anthropic_injects_web_search_tool(self):
        captured = {}

        def fake_post(url, **kwargs):
            captured['body'] = kwargs.get('json')
            return self._mock_http_response(self._anthropic_body('ok'))

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            self.provider._request_responses(
                inputs=[],
                enable_web_search=True,
            )
        tools = captured['body'].get('tools') or []
        types = [t.get('type') for t in tools]
        self.assertIn('web_search_20250305', types)

    def test_anthropic_injects_code_execution_tool(self):
        captured = {}

        def fake_post(url, **kwargs):
            captured['body'] = kwargs.get('json')
            return self._mock_http_response(self._anthropic_body('ok'))

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            self.provider._request_responses(
                inputs=[],
                enable_code_interpreter=True,
            )
        tools = captured['body'].get('tools') or []
        types = [t.get('type') for t in tools]
        self.assertIn('code_execution_20250825', types)

    def test_anthropic_ignores_image_generation_flag(self):
        captured = {}

        def fake_post(url, **kwargs):
            captured['body'] = kwargs.get('json')
            return self._mock_http_response(self._anthropic_body('ok'))

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            self.provider._request_responses(
                inputs=[],
                enable_image_generation=True,
            )
        self.assertNotIn('tools', captured['body'])

    def test_anthropic_usage_remaps_cache_tokens(self):
        body = self._anthropic_body('ok')
        body['usage'] = {
            'input_tokens': 100,
            'output_tokens': 20,
            'cache_read_input_tokens': 300,
            'cache_creation_input_tokens': 50,
        }

        def fake_post(url, **kwargs):
            return self._mock_http_response(body)

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            result = self.provider._request_responses(inputs=[])
        usage = result['usage']
        self.assertEqual(usage['input_tokens'], 450)
        self.assertEqual(usage['cache_read_tokens'], 300)
        self.assertEqual(usage['cache_write_tokens'], 50)

    def test_anthropic_anchors_cache_before_volatile_trailer(self):
        _system, messages, anchor = AnthropicProvider._inputs_to_messages(
            [
                {
                    'role': 'system',
                    'content': [{'type': 'input_text', 'text': 'sys'}],
                },
                {'role': 'user', 'content': [{'type': 'input_text', 'text': 'stable'}]},
                {
                    'role': 'user',
                    'content': [{'type': 'input_text', 'text': '<ui_ctx>x</ui_ctx>'}],
                    '_cache_volatile': True,
                },
            ]
        )
        self.assertEqual(anchor, (0, 0))
        self.assertEqual(messages[0]['content'][0]['text'], 'stable')
        self.assertEqual(messages[0]['content'][1]['text'], '<ui_ctx>x</ui_ctx>')

    def test_anthropic_places_conversation_cache_control_before_trailer(self):
        captured = {}

        def fake_post(url, **kwargs):
            captured['body'] = kwargs.get('json')
            return self._mock_http_response(self._anthropic_body('ok'))

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            self.provider._request_responses(
                inputs=[
                    {'role': 'user', 'content': [{'type': 'input_text', 'text': 'q'}]},
                    {
                        'role': 'user',
                        'content': [{'type': 'input_text', 'text': '<ui_ctx/>'}],
                        '_cache_volatile': True,
                    },
                ]
            )
        content = captured['body']['messages'][0]['content']
        self.assertEqual(content[0]['cache_control'], {'type': 'ephemeral'})
        self.assertNotIn('cache_control', content[1])

    def test_anthropic_skips_cache_control_for_non_claude_model(self):
        captured = {}

        def fake_post(url, **kwargs):
            captured['body'] = kwargs.get('json')
            return self._mock_http_response(self._anthropic_body('ok'))

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            self.provider._request_responses(
                inputs=[
                    {
                        'role': 'system',
                        'content': [{'type': 'input_text', 'text': 's'}],
                    },
                ],
                model='some-open-model',
            )
        self.assertEqual(captured['body']['system'], 's')

    def test_anthropic_connection_test_ok(self):
        def fake_post(url, **kwargs):
            return self._mock_http_response(self._anthropic_body('ok'))

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            self.assertTrue(self.provider._get_client().test_connection())
