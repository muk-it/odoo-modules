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
