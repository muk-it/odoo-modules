import json

from unittest.mock import patch

from odoo import api
from odoo.exceptions import AccessError
from odoo.tests import common
from odoo.tests.common import new_test_user

from odoo.addons.muk_mcp.core.tool import invalidate_registry_cache, mcp_tool


@api.model
@mcp_tool(
    name='mcp_test_log_probe',
    description='No-op probe for log-path coverage.',
    input_schema={'type': 'object', 'properties': {}},
    category='read',
)
def _mcp_test_log_probe(self):
    return {'ok': True}


class TestMcpLog(common.TransactionCase):

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.log_model = cls.env['muk_mcp.log']
        cls.session_model = cls.env['muk_mcp.session']
        cls.notification_model = cls.env['muk_mcp.notification']
        cls.tool_model = cls.env['muk_mcp.tool']
        cls.mixin_cls = type(cls.env['muk_mcp.mixin'])
        cls.startClassPatcher(patch.object(
            cls.mixin_cls, '_mcp_test_log_probe',
            _mcp_test_log_probe, create=True,
        ))
        invalidate_registry_cache(cls.env)
        cls.addClassCleanup(invalidate_registry_cache, cls.env)

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _make_notification(self, user, event_id):
        session = self.session_model.sudo().create({'user_id': user.id})
        return self.notification_model.sudo().create({
            'session_id': session.id,
            'event_id': event_id,
            'method': 'notifications/tools/list_changed',
        })

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_create_log_record(self):
        record = self.log_model.sudo().create({
            'user_id': self.env.user.id,
            'method': 'tools/call',
            'tool_name': 'search_read',
            'model_name': 'res.partner',
            'status': 'ok',
            'duration_ms': 42,
        })
        self.assertTrue(record)
        self.assertEqual(record.status, 'ok')
        self.assertEqual(record.duration_ms, 42)
        self.assertEqual(record.tool_name, 'search_read')

    def test_create_error_log(self):
        record = self.log_model.sudo().create({
            'user_id': self.env.user.id,
            'method': 'tools/call',
            'tool_name': 'create_records',
            'status': 'error',
            'error_message': 'Something went wrong',
        })
        self.assertEqual(record.status, 'error')
        self.assertEqual(record.error_message, 'Something went wrong')

    def test_create_denied_log(self):
        record = self.log_model.sudo().create({
            'user_id': self.env.user.id,
            'method': 'tools/call',
            'tool_name': 'delete_records',
            'model_name': 'sale.order',
            'status': 'denied',
        })
        self.assertEqual(record.status, 'denied')
        self.assertEqual(record.model_name, 'sale.order')

    def test_log_method_does_not_crash(self):
        self.log_model.log(
            user_id=self.env.user.id,
            method='test',
            status='ok',
        )

    def test_log_with_request_response_data(self):
        arguments = {'model': 'res.partner', 'domain': [], 'limit': 10}
        result = {'content': [{'type': 'text', 'text': '[]'}]}
        record = self.log_model.sudo().create({
            'user_id': self.env.user.id,
            'method': 'tools/call',
            'tool_name': 'search_read',
            'model_name': 'res.partner',
            'status': 'ok',
            'duration_ms': 15,
            'request_data': json.dumps(arguments, indent=4),
            'response_data': json.dumps(result, indent=4),
            'ip_address': '127.0.0.1',
        })
        self.assertEqual(record.ip_address, '127.0.0.1')
        self.assertIn('res.partner', record.request_data)
        self.assertIn('content', record.response_data)

    def test_log_with_record_linkage(self):
        record = self.log_model.sudo().create({
            'user_id': self.env.user.id,
            'method': 'tools/call',
            'tool_name': 'create_records',
            'model_name': 'res.partner',
            'res_id': 42,
            'res_ids': [42],
            'status': 'ok',
            'duration_ms': 10,
        })
        self.assertEqual(record.model_name, 'res.partner')
        self.assertEqual(record.res_id, 42)
        self.assertEqual(record.res_ids, [42])

    def test_log_method_with_new_fields(self):
        self.log_model.log(
            user_id=self.env.user.id,
            method='tools/call',
            tool_name='search_read',
            model_name='res.partner',
            status='ok',
            duration_ms=5,
            request_data='{"model": "res.partner"}',
            response_data='[{"id": 1}]',
            ip_address='192.168.1.1',
        )

    # ----------------------------------------------------------
    # Tests: in-process tool._call records a log row
    # ----------------------------------------------------------

    def _captured_log(self):
        captured = []

        def _capture(_self, **values):
            captured.append(values)

        return captured, patch.object(
            type(self.log_model), 'log', autospec=True, side_effect=_capture,
        )

    def test_tool_call_writes_log_on_success(self):
        captured, mock = self._captured_log()
        with mock:
            text, _info = self.tool_model._call(
                'mcp_test_log_probe', {}, self.env,
            )
        self.assertEqual(json.loads(text), {'ok': True})
        self.assertEqual(len(captured), 1)
        entry = captured[0]
        self.assertEqual(entry['method'], 'tools/call')
        self.assertEqual(entry['tool_name'], 'mcp_test_log_probe')
        self.assertEqual(entry['user_id'], self.env.uid)
        self.assertEqual(entry['status'], 'ok')
        self.assertNotIn('key_id', entry)
        self.assertIn('duration_ms', entry)

    def test_tool_call_writes_log_on_error(self):
        captured, mock = self._captured_log()
        with mock, self.assertRaises(Exception):
            self.tool_model._call('mcp_test_unknown_tool', {}, self.env)
        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0]['status'], 'error')
        self.assertEqual(captured[0]['tool_name'], 'mcp_test_unknown_tool')

    # ----------------------------------------------------------
    # Tests: record rule isolation
    # ----------------------------------------------------------

    def test_user_only_sees_their_own_log_rows(self):
        user = new_test_user(self.env, login='mcp_log_reader')
        mine = self.log_model.sudo().create({
            'user_id': user.id,
            'method': 'tools/call',
            'tool_name': 'mcp_log_mine',
            'status': 'ok',
        })
        theirs = self.log_model.sudo().create({
            'user_id': self.env.ref('base.user_admin').id,
            'method': 'tools/call',
            'tool_name': 'mcp_log_theirs',
            'request_data': '{"secret": "value"}',
            'status': 'ok',
        })
        visible = self.log_model.with_user(user).search(
            [('id', 'in', (mine + theirs).ids)],
        )
        self.assertEqual(visible, mine)
        with self.assertRaises(AccessError):
            theirs.with_user(user).read(['request_data'])

    def test_user_only_sees_notifications_of_their_own_sessions(self):
        user = new_test_user(self.env, login='mcp_notification_reader')
        mine = self._make_notification(user, 'mcp-log-mine')
        theirs = self._make_notification(
            self.env.ref('base.user_admin'), 'mcp-log-theirs',
        )
        visible = self.notification_model.with_user(user).search(
            [('id', 'in', (mine + theirs).ids)],
        )
        self.assertEqual(visible, mine)

    def test_user_cannot_write_create_or_unlink_notifications(self):
        user = new_test_user(self.env, login='mcp_notification_writer')
        mine = self._make_notification(user, 'mcp-log-write')
        with self.assertRaises(AccessError):
            mine.with_user(user).write({'delivered': True})
        with self.assertRaises(AccessError):
            self.notification_model.with_user(user).create({
                'session_id': mine.session_id.id,
                'event_id': 'mcp-log-forged',
                'method': 'notifications/tools/list_changed',
            })
        with self.assertRaises(AccessError):
            mine.with_user(user).unlink()
