import json

from odoo.tests import common


class TestMcpLog(common.TransactionCase):

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.log_model = cls.env['muk_mcp.log']

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
            'tool_name': 'create_record',
            'status': 'error',
            'error_message': 'Something went wrong',
        })
        self.assertEqual(record.status, 'error')
        self.assertEqual(record.error_message, 'Something went wrong')

    def test_create_denied_log(self):
        record = self.log_model.sudo().create({
            'user_id': self.env.user.id,
            'method': 'tools/call',
            'tool_name': 'delete_record',
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
            'tool_name': 'create_record',
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
