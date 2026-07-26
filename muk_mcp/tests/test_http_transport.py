from __future__ import annotations

import base64
import json
from typing import Any

from odoo import api, models
from odoo.tests import tagged
from odoo.tests.common import new_test_user

from odoo.addons.muk_mcp.core.tool import invalidate_registry_cache, mcp_tool
from odoo.addons.muk_mcp.tests.common import MCPHttpCase


@api.model
@mcp_tool(
    name='mcp_http_boom',
    description='Raise an unexpected error for transport tests.',
    input_schema={'type': 'object', 'properties': {}},
    category='read',
)
def _mcp_http_boom(self):
    message = 'kaboom'
    raise ValueError(message)


@tagged('post_install', '-at_install')
class TestMcpHttpTransport(MCPHttpCase):
    """Cover the authenticated JSON-RPC transport served at ``/mcp``."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.session_model = cls.env['muk_mcp.session']
        cls.notification_model = cls.env['muk_mcp.notification']
        cls.log_model = cls.env['muk_mcp.log']
        cls.mixin_cls = type(cls.env['muk_mcp.mixin'])
        cls.mixin_cls._mcp_http_boom = _mcp_http_boom
        invalidate_registry_cache(cls.env)

    @classmethod
    def tearDownClass(cls) -> None:
        delattr(cls.mixin_cls, '_mcp_http_boom')
        invalidate_registry_cache(cls.env)
        super().tearDownClass()

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _queue_notification(
        self,
        session: models.BaseModel,
        method: str,
    ) -> models.BaseModel:
        """Queue one undelivered notification on ``session`` and return it."""
        return self.notification_model.create(
            {
                'session_id': session.id,
                'event_id': 'evt-%s-%s' % (session.id, method),
                'method': method,
            },
        )

    def _tool_text(self, body: dict[str, Any]) -> str:
        """Return the first text content block of a ``tools/call`` result."""
        return body['result']['content'][0]['text']

    # ----------------------------------------------------------
    # Tests: request framing
    # ----------------------------------------------------------

    def test_malformed_json_body_is_a_parse_error(self):
        response = self.mcp_post(body='{not json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error']['code'], -32700)

    def test_scalar_json_bodies_are_parse_errors(self):
        for body in ('5', '"x"', 'true', 'null'):
            response = self.mcp_post(body=body)
            self.assertEqual(response.status_code, 400, body)
            self.assertEqual(response.json()['error']['code'], -32700, body)

    def test_missing_jsonrpc_member_is_an_invalid_request(self):
        response = self.mcp_post({'id': 1, 'method': 'ping'})
        self.assertEqual(response.status_code, 400)
        error = response.json()['error']
        self.assertEqual(error['code'], -32600)
        self.assertIn('jsonrpc', error['message'])

    def test_wrong_jsonrpc_version_is_an_invalid_request(self):
        response = self.mcp_post({'jsonrpc': '1.0', 'id': 1, 'method': 'ping'})
        self.assertEqual(response.json()['error']['code'], -32600)

    def test_missing_method_is_an_invalid_request(self):
        response = self.mcp_post({'jsonrpc': '2.0', 'id': 1})
        error = response.json()['error']
        self.assertEqual(error['code'], -32600)
        self.assertEqual(error['message'], 'Invalid Request: method is required')

    def test_non_string_method_is_an_invalid_request(self):
        response = self.mcp_post({'jsonrpc': '2.0', 'id': 1, 'method': 42})
        self.assertEqual(response.json()['error']['code'], -32600)

    def test_unknown_method_is_method_not_found(self):
        response = self.mcp_post(
            {'jsonrpc': '2.0', 'id': 1, 'method': 'does/not/exist'},
        )
        self.assertEqual(response.status_code, 200)
        error = response.json()['error']
        self.assertEqual(error['code'], -32601)
        self.assertIn('does/not/exist', error['message'])

    def test_notification_returns_an_empty_accepted_response(self):
        session_id = self.mcp_handshake()
        response = self.mcp_post(
            {'jsonrpc': '2.0', 'method': 'notifications/cancelled'},
            session_id=session_id,
        )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.content, b'')

    def test_id_less_call_still_receives_a_response(self):
        response = self.mcp_post({'jsonrpc': '2.0', 'method': 'ping'})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIsNone(body['id'])
        self.assertEqual(body['result'], {})

    def test_null_params_on_tools_call_is_a_clean_error(self):
        session_id = self.mcp_handshake()
        response = self.mcp_post(
            {
                'jsonrpc': '2.0',
                'id': 1,
                'method': 'tools/call',
                'params': None,
            },
            session_id=session_id,
        )
        body = response.json()
        self.assertNotIn('error', body)
        self.assertTrue(body['result']['isError'])
        self.assertEqual(self._tool_text(body), 'Tool name is required')
        self.assertNotIn('Traceback', response.text)
        self.assertNotIn('NoneType', response.text)

    def test_null_params_on_prompts_get_is_a_clean_error(self):
        session_id = self.mcp_handshake()
        response = self.mcp_post(
            {
                'jsonrpc': '2.0',
                'id': 1,
                'method': 'prompts/get',
                'params': None,
            },
            session_id=session_id,
        )
        error = response.json()['error']
        self.assertEqual(error['code'], -32603)
        self.assertIn('Prompt not found', error['message'])
        self.assertNotIn('Traceback', response.text)
        self.assertNotIn('NoneType', response.text)

    # ----------------------------------------------------------
    # Tests: content type
    # ----------------------------------------------------------

    def test_text_plain_body_is_not_parsed(self):
        response = self.mcp_post(self.mcp_ping(), content_type='text/plain')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error']['code'], -32700)

    def test_json_with_charset_parameter_is_parsed(self):
        response = self.mcp_post(
            self.mcp_ping(),
            content_type='application/json; charset=utf-8',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['result'], {})

    # ----------------------------------------------------------
    # Tests: batches
    # ----------------------------------------------------------

    def test_batch_returns_one_result_per_item_in_order(self):
        body = self.mcp_json([self.mcp_ping(1), self.mcp_ping(2)])
        self.assertEqual([entry['id'] for entry in body], [1, 2])
        self.assertEqual([entry['result'] for entry in body], [{}, {}])

    def test_empty_batch_is_a_single_invalid_request(self):
        response = self.mcp_post([])
        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertIsInstance(body, dict)
        self.assertEqual(body['error']['code'], -32600)

    def test_oversized_batch_is_rejected(self):
        response = self.mcp_post([self.mcp_ping(i) for i in range(21)])
        self.assertEqual(response.status_code, 400)
        error = response.json()['error']
        self.assertEqual(error['code'], -32600)
        self.assertIn('Batch too large', error['message'])

    def test_batch_drops_notification_results(self):
        session_id = self.mcp_handshake()
        body = self.mcp_json(
            [
                {'jsonrpc': '2.0', 'method': 'notifications/cancelled'},
                self.mcp_ping(7),
            ],
            session_id=session_id,
        )
        self.assertEqual(len(body), 1)
        self.assertEqual(body[0]['id'], 7)

    def test_batch_initialize_does_not_emit_the_session_header(self):
        response = self.mcp_post(
            [{'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {}}],
        )
        body = response.json()
        self.assertIn('protocolVersion', body[0]['result'])
        self.assertNotIn('Mcp-Session-Id', response.headers)

    # ----------------------------------------------------------
    # Tests: rate limiting
    # ----------------------------------------------------------

    def test_single_requests_are_charged_one_token_each(self):
        token, _key = self.make_mcp_key(
            self.mcp_user,
            name='Single Limited',
            rate_limit=2,
        )
        self.assertEqual(self.mcp_post(self.mcp_ping(), token=token).status_code, 200)
        self.assertEqual(self.mcp_post(self.mcp_ping(), token=token).status_code, 200)
        response = self.mcp_post(self.mcp_ping(), token=token)
        self.assertEqual(response.status_code, 429)
        body = response.json()
        self.assertEqual(body['jsonrpc'], '2.0')
        self.assertEqual(body['error']['code'], -32603)
        self.assertEqual(body['error']['message'], 'Rate limit exceeded')

    def test_batch_is_charged_exactly_its_item_count(self):
        token, _key = self.make_mcp_key(
            self.mcp_user,
            name='Batch Limited',
            rate_limit=2,
        )
        response = self.mcp_post([self.mcp_ping(1), self.mcp_ping(2)], token=token)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 2)
        follow_up = self.mcp_post(self.mcp_ping(3), token=token)
        self.assertEqual(follow_up.status_code, 429)

    def test_rate_limited_request_is_audited(self):
        token, key = self.make_mcp_key(
            self.mcp_user,
            name='Audited Limited',
            rate_limit=1,
        )
        self.mcp_post(self.mcp_ping(), token=token)
        self.mcp_post(self.mcp_ping(), token=token)
        log = self.log_model.search([('key_name', '=', key.name)])
        self.assertEqual(len(log), 1)
        self.assertEqual(log.status, 'rate_limited')

    # ----------------------------------------------------------
    # Tests: session lifecycle
    # ----------------------------------------------------------

    def test_initialize_returns_a_session_id_and_protocol_version(self):
        response = self.mcp_post(
            {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {}},
        )
        session_id = response.headers['Mcp-Session-Id']
        self.assertTrue(session_id)
        result = response.json()['result']
        self.assertEqual(result['protocolVersion'], '2025-03-26')
        self.assertTrue(result['capabilities']['tools']['listChanged'])
        session = self.session_model.search([('session_id', '=', session_id)])
        self.assertEqual(session.user_id, self.mcp_user)
        self.assertFalse(session.initialized)

    def test_ping_is_allowed_before_initialize(self):
        body = self.mcp_json(self.mcp_ping())
        self.assertEqual(body['result'], {})

    def test_tools_list_without_a_session_header_is_rejected(self):
        body = self.mcp_json({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'})
        self.assertEqual(body['error']['code'], -32600)
        self.assertEqual(body['error']['message'], 'Session required')

    def test_tools_list_on_an_uninitialized_session_is_rejected(self):
        response = self.mcp_post(
            {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {}},
        )
        session_id = response.headers['Mcp-Session-Id']
        body = self.mcp_json(
            {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'},
            session_id=session_id,
        )
        self.assertEqual(body['error']['code'], -32600)
        self.assertIn('not initialized', body['error']['message'])

    def test_session_of_another_user_is_treated_as_unknown(self):
        other = new_test_user(
            self.env,
            login='mcp_http_stranger',
            groups='base.group_user',
        )
        session = self.session_model.create(
            {'user_id': other.id, 'initialized': True},
        )
        body = self.mcp_json(
            {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'},
            session_id=session.session_id,
        )
        self.assertEqual(body['error']['code'], -32600)
        self.assertIn('not initialized', body['error']['message'])

    def test_tools_list_returns_the_mcp_registry(self):
        session_id = self.mcp_handshake()
        body = self.mcp_json(
            {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'},
            session_id=session_id,
        )
        names = {entry['name'] for entry in body['result']['tools']}
        self.assertIn('search_read', names)
        self.assertIn('whoami', names)

    def test_delete_deactivates_the_session(self):
        session_id = self.mcp_handshake()
        response = self.mcp_delete(session_id=session_id)
        self.assertEqual(response.status_code, 200)
        session = self.session_model.with_context(active_test=False).search(
            [('session_id', '=', session_id)],
        )
        self.assertFalse(session.active)

    # ----------------------------------------------------------
    # Tests: server-sent events
    # ----------------------------------------------------------

    def test_get_without_the_event_stream_accept_header_is_rejected(self):
        session_id = self.mcp_handshake()
        response = self.mcp_get(session_id=session_id)
        self.assertEqual(response.status_code, 405)

    def test_get_streams_queued_notifications(self):
        session_id = self.mcp_handshake()
        session = self.session_model.search([('session_id', '=', session_id)])
        self._queue_notification(session, 'notifications/tools/list_changed')
        response = self.mcp_get(
            session_id=session_id,
            headers={'Accept': 'text/event-stream'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            response.headers['Content-Type'].startswith('text/event-stream'),
        )
        self.assertIn('retry: 10000', response.text)
        self.assertIn('notifications/tools/list_changed', response.text)

    def test_last_event_id_of_another_session_does_not_shift_the_cursor(self):
        session_id = self.mcp_handshake()
        mine = self.session_model.search([('session_id', '=', session_id)])
        my_event = self._queue_notification(mine, 'notifications/tools/list_changed')
        other = self.session_model.create(
            {'user_id': self.mcp_user.id, 'initialized': True},
        )
        other_event = self._queue_notification(
            other,
            'notifications/prompts/list_changed',
        )
        self.assertGreater(other_event.id, my_event.id)
        response = self.mcp_get(
            session_id=session_id,
            headers={
                'Accept': 'text/event-stream',
                'Last-Event-ID': other_event.event_id,
            },
        )
        self.assertIn('notifications/tools/list_changed', response.text)

    # ----------------------------------------------------------
    # Tests: tools/call
    # ----------------------------------------------------------

    def test_tools_call_without_a_name_is_an_error_result(self):
        session_id = self.mcp_handshake()
        body = self.mcp_call_tool(session_id=session_id)
        self.assertTrue(body['result']['isError'])
        self.assertEqual(self._tool_text(body), 'Tool name is required')

    def test_tools_call_with_an_unknown_name_is_an_error_result(self):
        session_id = self.mcp_handshake()
        body = self.mcp_call_tool('no_such_tool', {}, session_id=session_id)
        self.assertTrue(body['result']['isError'])
        self.assertIn('Tool not found', self._tool_text(body))

    def test_tools_call_with_non_object_arguments_is_rejected_and_audited(self):
        session_id = self.mcp_handshake()
        body = self.mcp_call_tool('mcp_http_boom', ['a'], session_id=session_id)
        self.assertTrue(body['result']['isError'])
        self.assertIn('must be a JSON object', self._tool_text(body))
        log = self.log_model.search([('tool_name', '=', 'mcp_http_boom')])
        self.assertEqual(len(log), 1)
        self.assertEqual(log.status, 'error')
        self.assertIn('must be a JSON object', log.error_message)

    def test_tools_call_internal_error_does_not_leak_a_traceback(self):
        session_id = self.mcp_handshake()
        response = self.mcp_post(
            {
                'jsonrpc': '2.0',
                'id': 1,
                'method': 'tools/call',
                'params': {'name': 'mcp_http_boom', 'arguments': {}},
            },
            session_id=session_id,
        )
        body = response.json()
        self.assertTrue(body['result']['isError'])
        self.assertEqual(
            self._tool_text(body),
            'Internal server error: kaboom',
        )
        self.assertNotIn('Traceback', response.text)

    def test_tools_call_runs_as_the_key_owner(self):
        session_id = self.mcp_handshake()
        body = self.mcp_call_tool('whoami', {}, session_id=session_id)
        result = json.loads(self._tool_text(body))
        self.assertEqual(result['uid'], self.mcp_user.id)
        self.assertEqual(result['login'], self.mcp_user.login)

    def test_tools_call_export_denied_without_the_export_group(self):
        session_id = self.mcp_handshake()
        partner = self.env['res.partner'].create({'name': 'MCP Http Export'})
        body = self.mcp_call_tool(
            'export_records',
            {
                'model': 'res.partner',
                'fields': ['name'],
                'ids': [partner.id],
            },
            session_id=session_id,
        )
        self.assertTrue(body['result']['isError'])
        self.assertIn('rights to export data', self._tool_text(body))

    def test_tools_call_exports_csv_over_http(self):
        self.mcp_user.group_ids = [(4, self.env.ref('base.group_allow_export').id)]
        session_id = self.mcp_handshake()
        partner = self.env['res.partner'].create({'name': 'MCP Http Export'})
        body = self.mcp_call_tool(
            'export_records',
            {
                'model': 'res.partner',
                'fields': ['name'],
                'ids': [partner.id],
            },
            session_id=session_id,
        )
        result = json.loads(self._tool_text(body))
        self.assertEqual(result['row_count'], 1)
        content = base64.b64decode(result['content_base64']).decode('utf-8-sig')
        self.assertIn('MCP Http Export', content)
