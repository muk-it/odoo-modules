import json

from unittest.mock import MagicMock, patch

import requests

from odoo.addons.muk_ai_agentidoo.providers import agentidoo as agentidoo_mod

from .common import AgentidooTestCommon


class TestAgentidooProvider(AgentidooTestCommon):

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    def setUp(self):
        super().setUp()
        agentidoo_mod._capabilities_cache.clear()

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _sse_lines(self, events):
        lines = []
        for event_type, data in events:
            if event_type == '__comment__':
                lines.append(':keepalive')
                continue
            lines.append(f'event: {event_type}')
            lines.append(f'data: {json.dumps(data)}')
            lines.append('')
        return lines

    def _stream_response(self, events, status_code=200):
        response = MagicMock()
        response.status_code = status_code
        response.text = ''
        response.iter_lines.return_value = iter(self._sse_lines(events))
        response.__enter__ = lambda s: s
        response.__exit__ = lambda s, exc_type, exc, tb: False
        return response

    # ----------------------------------------------------------
    # Tests: request
    # ----------------------------------------------------------

    def test_request_creates_session_then_posts_message(self):
        calls = []

        def fake_post(url, **kwargs):
            calls.append({
                'url': url,
                'headers': kwargs.get('headers'),
                'body': kwargs.get('json'),
            })
            if url.endswith('/api/v1/chat/sessions'):
                return self._mock_response({'id': 'session_new'})
            return self._mock_response({'status': 'running'})

        def fake_get(url, **kwargs):
            return self._stream_response([
                ('text_delta', {'delta': 'pong'}),
                ('agent_end', {}),
            ])

        with patch.object(requests, 'post', side_effect=fake_post), \
                patch.object(requests, 'get', side_effect=fake_get):
            result = self.provider._request_responses(inputs=[
                {'role': 'user', 'content': [{'type': 'input_text', 'text': 'ping'}]},
            ])
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0]['url'], 'https://agentidoo.test/api/v1/chat/sessions')
        self.assertEqual(
            calls[1]['url'],
            'https://agentidoo.test/api/v1/chat/sessions/session_new/messages',
        )
        self.assertEqual(calls[1]['body'], {'content': 'ping'})
        self.assertEqual(calls[0]['headers']['Authorization'], 'Bearer ll_key_test')
        self.assertEqual(
            calls[0]['body']['metadata']['source'], 'muk_ai_agentidoo',
        )
        self.assertEqual(result['text'], 'pong')
        self.assertEqual(result['tool_calls'], [])
        self.assertEqual(
            result['carry_inputs'][0]['content'][0]['text'], 'pong',
        )

    def test_request_reuses_session_id_from_bag(self):
        bag = {'session_id': 'session_existing'}
        posts = []

        def fake_post(url, **kwargs):
            posts.append(url)
            return self._mock_response({'status': 'running'})

        def fake_get(url, **kwargs):
            return self._stream_response([('agent_end', {})])

        with patch.object(requests, 'post', side_effect=fake_post), \
                patch.object(requests, 'get', side_effect=fake_get):
            self.provider.with_context(agentidoo_bag=bag)._request_responses(
                inputs=[{
                    'role': 'user',
                    'content': [{'type': 'input_text', 'text': 'hi'}],
                }],
            )
        self.assertEqual(len(posts), 1)
        self.assertEqual(
            posts[0],
            'https://agentidoo.test/api/v1/chat/sessions/session_existing/messages',
        )

    def test_request_writes_new_session_id_to_bag(self):
        bag = {'session_id': ''}

        def fake_post(url, **kwargs):
            if url.endswith('/api/v1/chat/sessions'):
                return self._mock_response({'id': 'session_fresh'})
            return self._mock_response({'status': 'running'})

        def fake_get(url, **kwargs):
            return self._stream_response([('agent_end', {})])

        with patch.object(requests, 'post', side_effect=fake_post), \
                patch.object(requests, 'get', side_effect=fake_get):
            self.provider.with_context(agentidoo_bag=bag)._request_responses(
                inputs=[{
                    'role': 'user',
                    'content': [{'type': 'input_text', 'text': 'start'}],
                }],
            )
        self.assertEqual(bag['session_id'], 'session_fresh')

    def test_missing_api_key_raises(self):
        self.provider.sudo().api_key = ''
        with self.assertRaises(Exception):
            self.provider._request_responses(inputs=[
                {'role': 'user', 'content': [{'type': 'input_text', 'text': 'hi'}]},
            ])

    def test_test_connection_hits_me_v1_endpoint(self):
        captured = {}

        def fake_get(url, **kwargs):
            captured['url'] = url
            captured['headers'] = kwargs.get('headers')
            return self._mock_response({'authenticated': True})

        with patch.object(requests, 'get', side_effect=fake_get):
            self.provider._get_client().test_connection()
        self.assertEqual(captured['url'], 'https://agentidoo.test/api/v1/me')
        self.assertEqual(captured['headers']['Authorization'], 'Bearer ll_key_test')

    # ----------------------------------------------------------
    # Tests: SSE stream
    # ----------------------------------------------------------

    def test_sse_stream_collects_text_deltas_and_ignores_keepalive(self):
        deltas = []

        def fake_post(url, **kwargs):
            if url.endswith('/api/v1/chat/sessions'):
                return self._mock_response({'id': 'sess1'})
            return self._mock_response({'status': 'running'})

        def fake_get(url, **kwargs):
            return self._stream_response([
                ('__comment__', None),
                ('text_delta', {'delta': 'hel'}),
                ('text_delta', {'delta': 'lo'}),
                ('__comment__', None),
                ('text_delta', {'delta': ' world'}),
                ('agent_end', {}),
            ])

        def on_delta(kind, payload):
            if kind == 'text':
                deltas.append(payload['delta'])

        with patch.object(requests, 'post', side_effect=fake_post), \
                patch.object(requests, 'get', side_effect=fake_get):
            result = self.provider._request_responses(
                inputs=[{
                    'role': 'user',
                    'content': [{'type': 'input_text', 'text': 'hi'}],
                }],
                on_delta=on_delta,
            )
        self.assertEqual(result['text'], 'hello world')
        self.assertEqual(deltas, ['hel', 'lo', ' world'])

    def test_sse_stream_emits_tool_start_on_delta(self):
        events = []

        def fake_post(url, **kwargs):
            if url.endswith('/api/v1/chat/sessions'):
                return self._mock_response({'id': 'sess-tool'})
            return self._mock_response({'status': 'running'})

        def fake_get(url, **kwargs):
            return self._stream_response([
                ('tool_start', {'tool_call_id': 't1', 'tool_name': 'read_records'}),
                ('tool_args_delta', {'tool_call_id': 't1', 'delta': '{"mod'}),
                ('tool_args_delta', {'tool_call_id': 't1', 'delta': 'el":"res.partner"}'}),
                ('tool_result', {
                    'tool_call_id': 't1',
                    'tool_name': 'read_records',
                    'result': {'content': [{'type': 'text', 'text': 'ok'}]},
                }),
                ('text_delta', {'delta': 'done'}),
                ('agent_end', {}),
            ])

        def on_delta(kind, payload):
            events.append((kind, payload))

        with patch.object(requests, 'post', side_effect=fake_post), \
                patch.object(requests, 'get', side_effect=fake_get):
            result = self.provider._request_responses(
                inputs=[{
                    'role': 'user',
                    'content': [{'type': 'input_text', 'text': 'show partners'}],
                }],
                on_delta=on_delta,
            )
        kinds = [k for (k, _p) in events]
        self.assertIn('tool_start', kinds)
        self.assertIn('tool_args', kinds)
        self.assertEqual(result['tool_calls'], [])
        self.assertEqual(result['text'], 'done')
        start = next(p for (k, p) in events if k == 'tool_start')
        self.assertEqual(start, {'call_id': 't1', 'name': 'read_records'})

    def test_sse_stream_extracts_frontend_actions(self):
        frontend_output = {
            'content': [{
                'type': 'text',
                'text': json.dumps({
                    'status': 'validated',
                    'actions': [{'type': 'open_record', 'model': 'res.partner', 'id': 7}],
                }),
            }],
        }

        def fake_post(url, **kwargs):
            if url.endswith('/api/v1/chat/sessions'):
                return self._mock_response({'id': 'sess-fa'})
            return self._mock_response({'status': 'running'})

        def fake_get(url, **kwargs):
            return self._stream_response([
                ('tool_start', {'tool_call_id': 'fa1', 'tool_name': 'odoo_frontend_action'}),
                ('tool_result', {
                    'tool_call_id': 'fa1',
                    'tool_name': 'odoo_frontend_action',
                    'result': frontend_output,
                }),
                ('agent_end', {}),
            ])

        with patch.object(requests, 'post', side_effect=fake_post), \
                patch.object(requests, 'get', side_effect=fake_get):
            result = self.provider._request_responses(inputs=[{
                'role': 'user',
                'content': [{'type': 'input_text', 'text': 'open partner 7'}],
            }])
        self.assertEqual(
            result.get('agentidoo_frontend_actions'),
            [{'type': 'open_record', 'model': 'res.partner', 'id': 7}],
        )

    # ----------------------------------------------------------
    # Tests: capabilities cache
    # ----------------------------------------------------------

    def test_capabilities_cached_across_calls(self):
        calls = {'count': 0}

        def fake_get(url, **kwargs):
            calls['count'] += 1
            return self._mock_response({'features': ['streaming', 'tools']})

        with patch.object(requests, 'get', side_effect=fake_get):
            impl = self.provider._get_client()
            first = impl.capabilities()
            second = impl.capabilities()
        self.assertEqual(first, {'features': ['streaming', 'tools']})
        self.assertEqual(first, second)
        self.assertEqual(calls['count'], 1)
