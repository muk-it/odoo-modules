from __future__ import annotations

import copy
import json
from collections.abc import Sequence
from unittest.mock import MagicMock, patch

import requests

from odoo.exceptions import UserError
from odoo.tools import mute_logger

from odoo.addons.muk_ai.tests.common import AITestCommon
from odoo.addons.muk_ai.tools import build_tool_call_output


class TestAiOpenAIProvider(AITestCommon):
    """Verify the OpenAI provider request building, parsing, and streaming."""

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _sse_lines(self, events: Sequence[dict]) -> list[str]:
        """Render the events as the ``data:`` lines of an SSE stream."""
        lines = []
        for event in events:
            lines.append('data: ' + json.dumps(event))
            lines.append('')
        return lines

    def _mock_stream_response(self, events: Sequence[dict]) -> MagicMock:
        """Build a mocked streaming HTTP response replaying the given events."""
        response = MagicMock()
        response.iter_lines.return_value = iter(self._sse_lines(events))
        response.raise_for_status.return_value = None
        return response

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_request_responses_posts_to_responses_endpoint(self):
        captured = {}

        def fake_post(url, **kwargs):
            captured['url'] = url
            captured['body'] = kwargs.get('json')
            return self._mock_http_response(
                {
                    'output': [
                        {
                            'type': 'message',
                            'content': [{'text': 'ok'}],
                        }
                    ],
                    'usage': {'input_tokens': 5, 'output_tokens': 2},
                }
            )

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            result = self.provider._request_responses(
                inputs=[
                    {'role': 'user', 'content': [{'type': 'input_text', 'text': 'hi'}]}
                ],
            )
        self.assertTrue(captured['url'].endswith('/responses'))
        self.assertNotIn('prompt_cache_key', captured['body'])
        self.assertEqual(result['text'], 'ok')
        self.assertEqual(result['tool_calls'], [])
        self.assertEqual(result['usage']['input_tokens'], 5)

    def test_request_responses_sends_prompt_cache_key(self):
        captured = {}

        def fake_post(url, **kwargs):
            captured['body'] = kwargs.get('json')
            return self._mock_http_response(
                {'output': [], 'usage': {'input_tokens': 1, 'output_tokens': 1}}
            )

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            self.provider._request_responses(inputs=[], cache_key='muk_ai.session:42')
        self.assertEqual(captured['body']['prompt_cache_key'], 'muk_ai.session:42')

    def test_request_responses_sends_reasoning_effort(self):
        captured = {}

        def fake_post(url, **kwargs):
            captured['body'] = kwargs.get('json')
            return self._mock_http_response(
                {'output': [], 'usage': {'input_tokens': 1, 'output_tokens': 1}}
            )

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            self.provider._request_responses(
                inputs=[], model='gpt-5-mini', reasoning_effort='low'
            )
        self.assertEqual(captured['body']['reasoning']['effort'], 'low')

    def test_request_responses_defaults_reasoning_effort_to_medium(self):
        captured = {}

        def fake_post(url, **kwargs):
            captured['body'] = kwargs.get('json')
            return self._mock_http_response(
                {'output': [], 'usage': {'input_tokens': 1, 'output_tokens': 1}}
            )

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            self.provider._request_responses(inputs=[], model='gpt-5-mini')
        self.assertEqual(captured['body']['reasoning']['effort'], 'medium')

    def test_reasoning_effort_clamped_to_model_floor(self):
        self._create_model(
            'gpt-5.2-pro-test', reasoning_efforts=['medium', 'high', 'xhigh']
        )
        captured = {}

        def fake_post(url, **kwargs):
            captured['body'] = kwargs.get('json')
            return self._mock_http_response(
                {'output': [], 'usage': {'input_tokens': 1, 'output_tokens': 1}}
            )

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            self.provider._request_responses(
                inputs=[], model='gpt-5.2-pro-test', reasoning_effort='low'
            )
        self.assertEqual(captured['body']['reasoning']['effort'], 'medium')

    def test_reasoning_effort_above_floor_is_not_clamped(self):
        self._create_model(
            'gpt-5.2-pro-test', reasoning_efforts=['medium', 'high', 'xhigh']
        )
        captured = {}

        def fake_post(url, **kwargs):
            captured['body'] = kwargs.get('json')
            return self._mock_http_response(
                {'output': [], 'usage': {'input_tokens': 1, 'output_tokens': 1}}
            )

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            self.provider._request_responses(
                inputs=[], model='gpt-5.2-pro-test', reasoning_effort='high'
            )
        self.assertEqual(captured['body']['reasoning']['effort'], 'high')

    def test_reasoning_effort_clamped_to_model_ceiling(self):
        self._create_model(
            'gpt-5-test', reasoning_efforts=['minimal', 'low', 'medium', 'high']
        )
        captured = {}

        def fake_post(url, **kwargs):
            captured['body'] = kwargs.get('json')
            return self._mock_http_response(
                {'output': [], 'usage': {'input_tokens': 1, 'output_tokens': 1}}
            )

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            self.provider._request_responses(
                inputs=[], model='gpt-5-test', reasoning_effort='max'
            )
        self.assertEqual(captured['body']['reasoning']['effort'], 'high')

    def test_minimal_effort_clamped_up_by_model_floor(self):
        self._create_model('o3-test', reasoning_efforts=['low', 'medium', 'high'])
        captured = {}

        def fake_post(url, **kwargs):
            captured['body'] = kwargs.get('json')
            return self._mock_http_response(
                {'output': [], 'usage': {'input_tokens': 1, 'output_tokens': 1}}
            )

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            self.provider._request_responses(
                inputs=[], model='o3-test', reasoning_effort='minimal'
            )
        self.assertEqual(captured['body']['reasoning']['effort'], 'low')

    def test_xhigh_effort_passes_within_model_range(self):
        self._create_model(
            'gpt-5.2-test', reasoning_efforts=['low', 'medium', 'high', 'xhigh']
        )
        captured = {}

        def fake_post(url, **kwargs):
            captured['body'] = kwargs.get('json')
            return self._mock_http_response(
                {'output': [], 'usage': {'input_tokens': 1, 'output_tokens': 1}}
            )

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            self.provider._request_responses(
                inputs=[], model='gpt-5.2-test', reasoning_effort='xhigh'
            )
        self.assertEqual(captured['body']['reasoning']['effort'], 'xhigh')

    def test_unset_effort_uses_model_default(self):
        self._create_model(
            'gpt-5-default-test',
            reasoning_efforts=['low', 'medium', 'high'],
            reasoning_effort_default='high',
        )
        captured = {}

        def fake_post(url, **kwargs):
            captured['body'] = kwargs.get('json')
            return self._mock_http_response(
                {'output': [], 'usage': {'input_tokens': 1, 'output_tokens': 1}}
            )

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            self.provider._request_responses(inputs=[], model='gpt-5-default-test')
        self.assertEqual(captured['body']['reasoning']['effort'], 'high')

    def test_max_effort_passes_through_on_gpt_5_6(self):
        captured = {}

        def fake_post(url, **kwargs):
            captured['body'] = kwargs.get('json')
            return self._mock_http_response(
                {'output': [], 'usage': {'input_tokens': 1, 'output_tokens': 1}}
            )

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            self.provider._request_responses(
                inputs=[], model='gpt-5.6-sol', reasoning_effort='max'
            )
        self.assertEqual(captured['body']['reasoning']['effort'], 'max')

    def test_max_effort_clamped_to_xhigh_on_gpt_5_5(self):
        captured = {}

        def fake_post(url, **kwargs):
            captured['body'] = kwargs.get('json')
            return self._mock_http_response(
                {'output': [], 'usage': {'input_tokens': 1, 'output_tokens': 1}}
            )

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            self.provider._request_responses(
                inputs=[], model='gpt-5.5', reasoning_effort='max'
            )
        self.assertEqual(captured['body']['reasoning']['effort'], 'xhigh')

    @mute_logger('odoo.addons.muk_ai.providers.base')
    def test_rejected_effort_is_stripped_and_served(self):
        record = self.env.ref('muk_ai.model_gpt_5_mini')
        bodies = []

        def fake_post(url, **kwargs):
            bodies.append(copy.deepcopy(kwargs.get('json')))
            if len(bodies) == 1:
                response = self._mock_http_response({}, status_code=400)
                response.text = "Invalid value 'low' for 'reasoning.effort'."
                response.raise_for_status.side_effect = requests.HTTPError(
                    'bad request', response=response
                )
                return response
            return self._mock_http_response(
                {
                    'output': [{'type': 'message', 'content': [{'text': 'ok'}]}],
                    'usage': {'input_tokens': 1, 'output_tokens': 1},
                }
            )

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            result = self.provider._request_responses(
                inputs=[], model='gpt-5-mini', reasoning_effort='low'
            )
        self.assertEqual(len(bodies), 2)
        self.assertEqual(bodies[0]['reasoning']['effort'], 'low')
        self.assertEqual(bodies[1]['reasoning'], {'summary': 'detailed'})
        self.assertIn('include', bodies[1])
        self.assertEqual(result['text'], 'ok')
        self.assertIn('low', record.reasoning_efforts)
        self.assertFalse(record.notes)

    @mute_logger('odoo.addons.muk_ai.providers.base')
    def test_summary_rejection_spares_the_tier_catalog(self):
        record = self.env.ref('muk_ai.model_gpt_5_mini')
        bodies = []

        def fake_post(url, **kwargs):
            bodies.append(copy.deepcopy(kwargs.get('json')))
            reasoning = (kwargs.get('json') or {}).get('reasoning') or {}
            if 'summary' in reasoning:
                response = self._mock_http_response({}, status_code=400)
                response.text = (
                    'Your organization must be verified to generate '
                    'reasoning summaries.'
                )
                response.raise_for_status.side_effect = requests.HTTPError(
                    'bad request', response=response
                )
                return response
            return self._mock_http_response(
                {'output': [], 'usage': {'input_tokens': 1, 'output_tokens': 1}}
            )

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            result = self.provider._request_responses(
                inputs=[], model='gpt-5-mini', reasoning_effort='low'
            )
        self.assertEqual(len(bodies), 3)
        self.assertEqual(bodies[1]['reasoning'], {'summary': 'detailed'})
        self.assertNotIn('reasoning', bodies[2])
        self.assertNotIn('include', bodies[2])
        self.assertIn('low', record.reasoning_efforts)
        self.assertFalse(result['tool_calls'])

    def test_unrelated_error_is_not_retried(self):
        bodies = []

        def fake_post(url, **kwargs):
            bodies.append(kwargs.get('json'))
            response = self._mock_http_response({}, status_code=500)
            response.text = 'server exploded'
            response.raise_for_status.side_effect = requests.HTTPError(
                'boom', response=response
            )
            return response

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            with self.assertRaises(UserError):
                self.provider._request_responses(
                    inputs=[], model='gpt-5-mini', reasoning_effort='low'
                )
        self.assertEqual(len(bodies), 1)

    def test_request_responses_parses_tool_calls(self):
        response = self._mock_http_response(
            {
                'output': [
                    {
                        'type': 'function_call',
                        'name': 'list_modules',
                        'arguments': '{"installed_only": true}',
                        'call_id': 'call_1',
                    }
                ],
                'usage': {},
            }
        )
        with patch.object(requests.Session, 'post', return_value=response):
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

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            self.provider._request_responses(
                inputs=[],
                tools_schema=[{'type': 'function', 'name': 'x', 'parameters': {}}],
            )
        self.assertIn('tools', captured['body'])
        self.assertTrue(captured['body']['parallel_tool_calls'])

    def test_request_responses_sends_text_schema(self):
        captured = {}

        def fake_post(url, **kwargs):
            captured['body'] = kwargs.get('json')
            return self._mock_http_response({'output': [], 'usage': {}})

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            self.provider._request_responses(
                inputs=[],
                text_schema={'name': 'plan', 'schema': {'type': 'object'}},
            )
        self.assertEqual(captured['body']['text']['format']['type'], 'json_schema')

    def test_request_responses_raises_on_http_error(self):
        response = self._mock_http_response({}, status_code=500)
        response.text = 'server error'
        response.raise_for_status.side_effect = requests.HTTPError(
            'boom', response=response
        )
        with patch.object(requests.Session, 'post', return_value=response):
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
        response = self._mock_http_response(
            {
                'output': [{'type': 'message', 'content': [{'text': 'ok'}]}],
                'usage': {},
            }
        )
        with patch.object(requests.Session, 'post', return_value=response):
            self.assertTrue(self.provider._get_client().test_connection())

    def test_test_connection_raises_on_empty_text(self):
        response = self._mock_http_response({'output': [], 'usage': {}})
        with patch.object(requests.Session, 'post', return_value=response):
            with self.assertRaises(UserError):
                self.provider._get_client().test_connection()

    def test_request_responses_sends_max_output_tokens(self):
        self.provider.max_tokens = 2048
        captured = {}

        def fake_post(url, **kwargs):
            captured['body'] = kwargs.get('json')
            return self._mock_http_response({'output': [], 'usage': {}})

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            self.provider._request_responses(inputs=[])
        self.assertEqual(captured['body']['max_output_tokens'], 2048)

    def test_request_responses_omits_max_tokens_when_zero(self):
        self.provider.max_tokens = 0
        captured = {}

        def fake_post(url, **kwargs):
            captured['body'] = kwargs.get('json')
            return self._mock_http_response({'output': [], 'usage': {}})

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            self.provider._request_responses(inputs=[])
        self.assertNotIn('max_output_tokens', captured['body'])

    def test_request_responses_uses_model_kwarg(self):
        captured = {}

        def fake_post(url, **kwargs):
            captured['body'] = kwargs.get('json')
            return self._mock_http_response({'output': [], 'usage': {}})

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            self.provider._request_responses(inputs=[], model='gpt-4o')
        self.assertEqual(captured['body']['model'], 'gpt-4o')

    def test_openai_injects_web_search_tool(self):
        captured = {}

        def fake_post(url, **kwargs):
            captured['body'] = kwargs.get('json')
            return self._mock_http_response({'output': [], 'usage': {}})

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            self.provider._request_responses(
                inputs=[],
                enable_web_search=True,
            )
        types = [t.get('type') for t in captured['body'].get('tools') or []]
        self.assertIn('web_search', types)

    def test_openai_injects_image_generation_tool(self):
        captured = {}

        def fake_post(url, **kwargs):
            captured['body'] = kwargs.get('json')
            return self._mock_http_response({'output': [], 'usage': {}})

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            self.provider._request_responses(
                inputs=[],
                enable_image_generation=True,
            )
        types = [t.get('type') for t in captured['body'].get('tools') or []]
        self.assertIn('image_generation', types)

    def test_openai_injects_code_interpreter_tool(self):
        captured = {}

        def fake_post(url, **kwargs):
            captured['body'] = kwargs.get('json')
            return self._mock_http_response({'output': [], 'usage': {}})

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            self.provider._request_responses(
                inputs=[],
                enable_code_interpreter=True,
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

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            self.provider._request_responses(inputs=[])
        self.assertNotIn('tools', captured['body'])

    def test_request_responses_switches_to_stream_when_on_delta(self):
        response = self._mock_stream_response(
            [
                {'type': 'response.output_text.delta', 'delta': 'hi'},
                {
                    'type': 'response.completed',
                    'response': {
                        'output': [],
                        'usage': {'input_tokens': 1, 'output_tokens': 1},
                    },
                },
            ]
        )
        captured = {}

        def fake_post(url, **kwargs):
            captured['stream'] = kwargs.get('stream')
            captured['body'] = kwargs.get('json')
            return response

        deltas = []
        with patch.object(requests.Session, 'post', side_effect=fake_post):
            result = self.provider._request_responses(
                inputs=[],
                on_delta=lambda k, p: deltas.append((k, p)),
            )
        self.assertTrue(captured['stream'])
        self.assertTrue(captured['body']['stream'])
        self.assertEqual(result['text'], 'hi')
        self.assertEqual(deltas[0], ('text', {'delta': 'hi'}))

    def test_stream_emits_text_and_tool_deltas(self):
        response = self._mock_stream_response(
            [
                {'type': 'response.output_text.delta', 'delta': 'He'},
                {'type': 'response.output_text.delta', 'delta': 'llo'},
                {
                    'type': 'response.output_item.added',
                    'output_index': 0,
                    'item': {
                        'type': 'function_call',
                        'call_id': 'c1',
                        'name': 'do_it',
                    },
                },
                {
                    'type': 'response.function_call_arguments.delta',
                    'output_index': 0,
                    'delta': '{"a":',
                },
                {
                    'type': 'response.function_call_arguments.delta',
                    'output_index': 0,
                    'delta': '1}',
                },
                {
                    'type': 'response.output_item.done',
                    'output_index': 0,
                    'item': {
                        'type': 'function_call',
                        'call_id': 'c1',
                        'name': 'do_it',
                        'arguments': '{"a":1}',
                    },
                },
                {
                    'type': 'response.completed',
                    'response': {
                        'output': [],
                        'usage': {
                            'input_tokens': 11,
                            'output_tokens': 4,
                            'input_tokens_details': {'cached_tokens': 3},
                        },
                    },
                },
            ]
        )
        deltas = []
        with patch.object(requests.Session, 'post', return_value=response):
            result = self.provider._request_responses(
                inputs=[],
                on_delta=lambda k, p: deltas.append((k, p)),
            )
        text_deltas = [p['delta'] for (k, p) in deltas if k == 'text']
        tool_starts = [p for (k, p) in deltas if k == 'tool_start']
        tool_args = [p for (k, p) in deltas if k == 'tool_args']
        self.assertEqual(text_deltas, ['He', 'llo'])
        self.assertEqual(tool_starts, [{'call_id': 'c1', 'name': 'do_it'}])
        self.assertEqual(''.join(p['delta'] for p in tool_args), '{"a":1}')
        self.assertEqual(result['text'], 'Hello')
        self.assertEqual(len(result['tool_calls']), 1)
        self.assertEqual(result['tool_calls'][0]['arguments'], {'a': 1})
        self.assertEqual(result['carry_inputs'][0]['type'], 'function_call')
        self.assertEqual(result['usage']['input_tokens'], 11)
        self.assertEqual(result['usage']['cache_read_tokens'], 3)

    def test_stream_renders_image_partial_and_done(self):
        response = self._mock_stream_response(
            [
                {
                    'type': 'response.image_generation_call.partial_image',
                    'item_id': 'img1',
                    'partial_image_b64': 'AAAA',
                },
                {
                    'type': 'response.output_item.done',
                    'item': {
                        'type': 'image_generation_call',
                        'id': 'img1',
                    },
                },
                {
                    'type': 'response.completed',
                    'response': {
                        'output': [],
                        'usage': {'input_tokens': 2, 'output_tokens': 1},
                    },
                },
            ]
        )
        deltas = []
        with patch.object(requests.Session, 'post', return_value=response):
            result = self.provider._request_responses(
                inputs=[],
                enable_image_generation=True,
                on_delta=lambda k, p: deltas.append((k, p)),
            )
        self.assertIn('![generated image](data:image/png;base64,AAAA)', result['text'])
        text_payloads = [p for (k, p) in deltas if k == 'text']
        self.assertTrue(any('generated image' in p['delta'] for p in text_payloads))

    def test_stream_renders_code_interpreter_on_item_done(self):
        response = self._mock_stream_response(
            [
                {
                    'type': 'response.output_item.done',
                    'item': {
                        'type': 'code_interpreter_call',
                        'id': 'ci1',
                        'code': 'print(1)\n',
                        'results': [
                            {'type': 'logs', 'logs': '1\n'},
                            {'type': 'files', 'files': [{'name': 'plot.png'}]},
                        ],
                    },
                },
                {
                    'type': 'response.completed',
                    'response': {
                        'output': [],
                        'usage': {'input_tokens': 1, 'output_tokens': 1},
                    },
                },
            ]
        )
        with patch.object(requests.Session, 'post', return_value=response):
            result = self.provider._request_responses(
                inputs=[], on_delta=lambda k, p: None
            )
        self.assertIn('```python', result['text'])
        self.assertIn('print(1)', result['text'])
        self.assertIn('plot.png', result['text'])

    def test_stream_picks_up_message_from_response_completed(self):
        response = self._mock_stream_response(
            [
                {
                    'type': 'response.completed',
                    'response': {
                        'output': [
                            {
                                'type': 'message',
                                'role': 'assistant',
                                'content': [{'type': 'output_text', 'text': 'final'}],
                            }
                        ],
                        'usage': {'input_tokens': 1, 'output_tokens': 1},
                    },
                },
            ]
        )
        with patch.object(requests.Session, 'post', return_value=response):
            result = self.provider._request_responses(
                inputs=[],
                on_delta=lambda k, p: None,
            )
        kinds = {item['type'] for item in result['carry_inputs']}
        self.assertIn('message', kinds)

    def test_stream_image_call_on_response_completed_uses_cached_b64(self):
        response = self._mock_stream_response(
            [
                {
                    'type': 'response.image_generation_call.partial_image',
                    'item_id': 'imgZ',
                    'partial_image_b64': 'ZZZ',
                },
                {
                    'type': 'response.completed',
                    'response': {
                        'output': [{'type': 'image_generation_call', 'id': 'imgZ'}],
                        'usage': {'input_tokens': 1, 'output_tokens': 1},
                    },
                },
            ]
        )
        with patch.object(requests.Session, 'post', return_value=response):
            result = self.provider._request_responses(
                inputs=[],
                on_delta=lambda k, p: None,
            )
        self.assertIn('ZZZ', result['text'])

    def test_stream_code_call_on_response_completed(self):
        response = self._mock_stream_response(
            [
                {
                    'type': 'response.completed',
                    'response': {
                        'output': [
                            {
                                'type': 'code_interpreter_call',
                                'id': 'ci_comp',
                                'code': 'x = 1',
                                'results': [],
                            }
                        ],
                        'usage': {'input_tokens': 1, 'output_tokens': 1},
                    },
                },
            ]
        )
        with patch.object(requests.Session, 'post', return_value=response):
            result = self.provider._request_responses(
                inputs=[],
                on_delta=lambda k, p: None,
            )
        self.assertIn('x = 1', result['text'])

    def test_reasoning_error_after_streamed_content_is_not_retried(self):
        posts = []
        deltas = []

        def fake_post(url, **kwargs):
            posts.append(kwargs.get('json'))
            return self._mock_stream_response(
                [
                    {'type': 'response.output_text.delta', 'delta': 'partial'},
                    {
                        'type': 'response.error',
                        'error': {'message': "invalid 'reasoning.effort' value"},
                    },
                ]
            )

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            with self.assertRaises(UserError):
                self.provider._request_responses(
                    inputs=[],
                    model='gpt-5-mini',
                    reasoning_effort='low',
                    on_delta=lambda kind, data: deltas.append((kind, data)),
                )
        self.assertEqual(len(posts), 1)
        self.assertTrue(deltas)

    def test_stream_incomplete_captures_usage_and_appends_notice(self):
        response = self._mock_stream_response(
            [
                {'type': 'response.output_text.delta', 'delta': 'partial'},
                {
                    'type': 'response.incomplete',
                    'response': {
                        'output': [],
                        'incomplete_details': {'reason': 'max_output_tokens'},
                        'usage': {'input_tokens': 20, 'output_tokens': 4096},
                    },
                },
            ]
        )
        deltas = []
        with patch.object(requests.Session, 'post', return_value=response):
            result = self.provider._request_responses(
                inputs=[],
                on_delta=lambda k, p: deltas.append((k, p)),
            )
        self.assertEqual(result['usage']['input_tokens'], 20)
        self.assertEqual(result['usage']['output_tokens'], 4096)
        self.assertIn('partial', result['text'])
        self.assertIn('Max Tokens', result['text'])
        self.assertIn('4096', result['text'])
        text_deltas = [p['delta'] for (k, p) in deltas if k == 'text']
        self.assertTrue(any('Max Tokens' in d for d in text_deltas))

    def test_stream_incomplete_without_text_still_yields_notice(self):
        response = self._mock_stream_response(
            [
                {
                    'type': 'response.incomplete',
                    'response': {
                        'output': [{'type': 'reasoning', 'id': 'rs_1', 'summary': []}],
                        'incomplete_details': {'reason': 'max_output_tokens'},
                        'usage': {'input_tokens': 15, 'output_tokens': 4096},
                    },
                },
            ]
        )
        with patch.object(requests.Session, 'post', return_value=response):
            result = self.provider._request_responses(
                inputs=[],
                on_delta=lambda k, p: None,
            )
        self.assertTrue(result['text'])
        self.assertIn('Max Tokens', result['text'])
        self.assertEqual(result['usage']['output_tokens'], 4096)
        self.assertEqual(result['carry_inputs'][0]['type'], 'reasoning')

    def test_stream_error_event_raises_user_error(self):
        response = self._mock_stream_response(
            [
                {'type': 'response.error', 'error': {'message': 'bad stream'}},
            ]
        )
        with patch.object(requests.Session, 'post', return_value=response):
            with self.assertRaises(UserError):
                self.provider._request_responses(
                    inputs=[],
                    on_delta=lambda k, p: None,
                )

    # ----------------------------------------------------------
    # Attachments
    # ----------------------------------------------------------

    def test_attachment_image_becomes_input_image(self):
        captured = {}

        def fake_post(url, **kwargs):
            captured['body'] = kwargs.get('json')
            return self._mock_http_response({'output': [], 'usage': {}})

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
                ]
            )
        block = captured['body']['input'][0]['content'][0]
        self.assertEqual(block['type'], 'input_image')
        self.assertEqual(block['image_url'], 'data:image/png;base64,AAA=')

    def test_attachment_file_becomes_input_file(self):
        captured = {}

        def fake_post(url, **kwargs):
            captured['body'] = kwargs.get('json')
            return self._mock_http_response({'output': [], 'usage': {}})

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
                                'data_b64': 'AAA=',
                                'filename': 'doc.pdf',
                            }
                        ],
                    }
                ]
            )
        block = captured['body']['input'][0]['content'][0]
        self.assertEqual(block['type'], 'input_file')
        self.assertEqual(block['filename'], 'doc.pdf')
        self.assertEqual(block['file_data'], 'data:application/pdf;base64,AAA=')

    def test_attachment_inline_text_prefixes_filename(self):
        captured = {}

        def fake_post(url, **kwargs):
            captured['body'] = kwargs.get('json')
            return self._mock_http_response({'output': [], 'usage': {}})

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            self.provider._request_responses(
                inputs=[
                    {
                        'role': 'user',
                        'content': [
                            {
                                'type': 'muk_ai_attachment',
                                'strategy': 'text',
                                'mimetype': 'text/plain',
                                'inline_text': 'hello body',
                                'filename': 'note.txt',
                            }
                        ],
                    }
                ]
            )
        text = captured['body']['input'][0]['content'][0]['text']
        self.assertTrue(text.startswith('--- File: note.txt (text/plain) ---'))
        self.assertIn('hello body', text)
        self.assertNotIn('[truncated]', text)

    def test_attachment_inline_text_appends_truncated_marker(self):
        captured = {}

        def fake_post(url, **kwargs):
            captured['body'] = kwargs.get('json')
            return self._mock_http_response({'output': [], 'usage': {}})

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            self.provider._request_responses(
                inputs=[
                    {
                        'role': 'user',
                        'content': [
                            {
                                'type': 'muk_ai_attachment',
                                'strategy': 'text',
                                'inline_text': 'partial',
                                'truncated': True,
                            }
                        ],
                    }
                ]
            )
        text = captured['body']['input'][0]['content'][0]['text']
        self.assertIn('[truncated]', text)

    def test_attachment_rewrite_passes_through_non_list_content(self):
        captured = {}

        def fake_post(url, **kwargs):
            captured['body'] = kwargs.get('json')
            return self._mock_http_response({'output': [], 'usage': {}})

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            self.provider._request_responses(
                inputs=[
                    {'role': 'user', 'content': 'plain string'},
                ]
            )
        self.assertEqual(captured['body']['input'][0]['content'], 'plain string')

    # ----------------------------------------------------------
    # Parse non-streaming
    # ----------------------------------------------------------

    def test_parse_renders_image_generation_call_output(self):
        response = self._mock_http_response(
            {
                'output': [
                    {
                        'type': 'image_generation_call',
                        'status': 'completed',
                        'result': 'BASE64IMG',
                    }
                ],
                'usage': {},
            }
        )
        with patch.object(requests.Session, 'post', return_value=response):
            result = self.provider._request_responses(inputs=[])
        self.assertIn('data:image/png;base64,BASE64IMG', result['text'])

    def test_parse_skips_failed_image_generation_call(self):
        response = self._mock_http_response(
            {
                'output': [
                    {
                        'type': 'image_generation_call',
                        'status': 'failed',
                        'result': '',
                    }
                ],
                'usage': {},
            }
        )
        with patch.object(requests.Session, 'post', return_value=response):
            result = self.provider._request_responses(inputs=[])
        self.assertEqual(result['text'], '')

    def test_parse_renders_code_interpreter_call_output(self):
        response = self._mock_http_response(
            {
                'output': [
                    {
                        'type': 'code_interpreter_call',
                        'code': 'print("hi")',
                        'results': [{'type': 'logs', 'logs': 'hi\n'}],
                    }
                ],
                'usage': {},
            }
        )
        with patch.object(requests.Session, 'post', return_value=response):
            result = self.provider._request_responses(inputs=[])
        self.assertIn('```python', result['text'])
        self.assertIn('print("hi")', result['text'])
        self.assertIn('hi', result['text'])

    def test_parse_incomplete_status_appends_truncation_notice(self):
        response = self._mock_http_response(
            {
                'status': 'incomplete',
                'incomplete_details': {'reason': 'max_output_tokens'},
                'output': [{'type': 'message', 'content': [{'text': 'partial'}]}],
                'usage': {'input_tokens': 9, 'output_tokens': 4096},
            }
        )
        with patch.object(requests.Session, 'post', return_value=response):
            result = self.provider._request_responses(inputs=[])
        self.assertIn('partial', result['text'])
        self.assertIn('Max Tokens', result['text'])
        self.assertEqual(result['usage']['output_tokens'], 4096)

    def test_parse_captures_bare_text_on_line(self):
        response = self._mock_http_response(
            {
                'output': [{'type': 'unknown', 'text': 'stray piece'}],
                'usage': {},
            }
        )
        with patch.object(requests.Session, 'post', return_value=response):
            result = self.provider._request_responses(inputs=[])
        self.assertEqual(result['text'], 'stray piece')
