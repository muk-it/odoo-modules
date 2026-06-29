import json
import secrets
from unittest.mock import patch

from odoo import api
from odoo.tests import common, tagged

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


@tagged('post_install', '-at_install')
class TestMcpLog(common.TransactionCase):
    """Verify audit log records and the log rows emitted on tool execution."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.log_model = cls.env['muk_mcp.log']
        cls.tool_model = cls.env['muk_mcp.tool']
        cls.mixin_cls = type(cls.env['muk_mcp.mixin'])
        cls.mixin_cls._mcp_test_log_probe = _mcp_test_log_probe
        invalidate_registry_cache(cls.env)

    @classmethod
    def tearDownClass(cls):
        delattr(cls.mixin_cls, '_mcp_test_log_probe')
        invalidate_registry_cache(cls.env)
        super().tearDownClass()

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_create_log_record(self):
        record = self.log_model.sudo().create(
            {
                'user_id': self.env.user.id,
                'method': 'tools/call',
                'tool_name': 'search_read',
                'model_name': 'res.partner',
                'status': 'ok',
                'duration_ms': 42,
            },
        )
        self.assertTrue(record)
        self.assertEqual(record.status, 'ok')
        self.assertEqual(record.duration_ms, 42)
        self.assertEqual(record.tool_name, 'search_read')

    def test_create_error_log(self):
        record = self.log_model.sudo().create(
            {
                'user_id': self.env.user.id,
                'method': 'tools/call',
                'tool_name': 'create_records',
                'status': 'error',
                'error_message': 'Something went wrong',
            },
        )
        self.assertEqual(record.status, 'error')
        self.assertEqual(record.error_message, 'Something went wrong')

    def test_create_denied_log(self):
        record = self.log_model.sudo().create(
            {
                'user_id': self.env.user.id,
                'method': 'tools/call',
                'tool_name': 'delete_records',
                'model_name': 'sale.order',
                'status': 'denied',
            },
        )
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
        record = self.log_model.sudo().create(
            {
                'user_id': self.env.user.id,
                'method': 'tools/call',
                'tool_name': 'search_read',
                'model_name': 'res.partner',
                'status': 'ok',
                'duration_ms': 15,
                'request_data': json.dumps(arguments, indent=4),
                'response_data': json.dumps(result, indent=4),
                'ip_address': '127.0.0.1',
            },
        )
        self.assertEqual(record.ip_address, '127.0.0.1')
        self.assertIn('res.partner', record.request_data)
        self.assertIn('content', record.response_data)

    def test_log_with_record_linkage(self):
        record = self.log_model.sudo().create(
            {
                'user_id': self.env.user.id,
                'method': 'tools/call',
                'tool_name': 'create_records',
                'model_name': 'res.partner',
                'res_id': 42,
                'res_ids': [42],
                'status': 'ok',
                'duration_ms': 10,
            },
        )
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
            type(self.log_model),
            'log',
            autospec=True,
            side_effect=_capture,
        )

    def test_tool_call_writes_log_on_success(self):
        captured, mock = self._captured_log()
        with mock:
            text, _info = self.tool_model._call(
                'mcp_test_log_probe',
                {},
                self.env,
            )
        self.assertEqual(json.loads(text), {'ok': True})
        self.assertEqual(len(captured), 1)
        entry = captured[0]
        self.assertEqual(entry['method'], 'tools/call')
        self.assertEqual(entry['tool_name'], 'mcp_test_log_probe')
        self.assertEqual(entry['user_id'], self.env.uid)
        self.assertEqual(entry['status'], 'ok')
        self.assertNotIn('key_name', entry)
        self.assertIn('duration_ms', entry)

    def test_tool_call_writes_log_on_error(self):
        captured, mock = self._captured_log()
        with mock, self.assertRaises(Exception):
            self.tool_model._call('mcp_test_unknown_tool', {}, self.env)
        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0]['status'], 'error')
        self.assertEqual(captured[0]['tool_name'], 'mcp_test_unknown_tool')

    # ----------------------------------------------------------
    # Tests: key snapshot must survive key deletion
    # ----------------------------------------------------------

    def test_key_snapshot_survives_key_deletion(self):
        key_model = self.env['muk_mcp.key']
        raw_token = secrets.token_urlsafe(32)
        key = key_model.create(
            {
                'name': 'Doomed Key',
                'user_id': self.env.user.id,
                'key_hash': key_model._hash_key(raw_token),
                'key_prefix': raw_token[:8],
            },
        )
        record = self.log_model.sudo().create(
            {
                'key_name': key.name,
                'key_prefix': key.key_prefix,
                'user_id': self.env.user.id,
                'method': 'tools/call',
                'tool_name': 'search_read',
                'status': 'ok',
            },
        )
        key.unlink()
        self.assertTrue(record.exists())
        self.assertEqual(record.key_name, 'Doomed Key')
        self.assertEqual(record.key_prefix, raw_token[:8])
        self.assertEqual(
            record.read(['key_name'])[0]['key_name'],
            'Doomed Key',
        )
