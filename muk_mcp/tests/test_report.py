import base64
import json

from odoo.exceptions import UserError
from odoo.tests import common


class TestMcpPrintReport(common.TransactionCase):

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tool_model = cls.env['muk_mcp.tool']
        cls.env['ir.ui.view'].create({
            'type': 'qweb',
            'name': 'muk_mcp.test_print_report',
            'key': 'muk_mcp.test_print_report',
            'arch': (
                '<t t-name="muk_mcp.test_print_report">'
                '<t t-foreach="docs" t-as="d">'
                '<t t-esc="d.name"/>|'
                '</t>'
                '</t>'
            ),
        })
        cls.report = cls.env['ir.actions.report'].create({
            'name': 'MCP Test Report',
            'report_name': 'muk_mcp.test_print_report',
            'report_type': 'qweb-text',
            'model': 'res.partner',
        })
        cls.partner = cls.env['res.partner'].create({
            'name': 'MCP Print Target',
        })

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _call(self, name, arguments):
        text, _info = self.tool_model._call(name, arguments, self.env)
        return json.loads(text)

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_print_by_id_returns_base64(self):
        result = self._call('print_report', {
            'report_ref': self.report.id,
            'ids': [self.partner.id],
        })
        self.assertIn('filename', result)
        self.assertIn('mimetype', result)
        self.assertIn('content_base64', result)
        self.assertEqual(result['mimetype'], 'text/plain')
        self.assertTrue(result['filename'].endswith('.txt'))
        decoded = base64.b64decode(result['content_base64']).decode()
        self.assertIn('MCP Print Target', decoded)

    def test_print_by_report_name(self):
        result = self._call('print_report', {
            'report_ref': 'muk_mcp.test_print_report',
            'ids': [self.partner.id],
        })
        decoded = base64.b64decode(result['content_base64']).decode()
        self.assertIn('MCP Print Target', decoded)

    def test_print_by_xmlid_prefix(self):
        xmlid = self.report.get_external_id().get(self.report.id)
        if not xmlid:
            self.env['ir.model.data'].create({
                'name': 'muk_mcp_test_action_print_report',
                'module': 'muk_mcp',
                'model': 'ir.actions.report',
                'res_id': self.report.id,
            })
            xmlid = 'muk_mcp.muk_mcp_test_action_print_report'
        result = self._call('print_report', {
            'report_ref': xmlid,
            'ids': [self.partner.id],
        })
        self.assertIn('content_base64', result)

    def test_print_unknown_xmlid_raises(self):
        with self.assertRaises(UserError):
            self._call('print_report', {
                'report_ref': 'muk_mcp.nonexistent_xmlid',
                'ids': [self.partner.id],
            })

    def test_print_unknown_report_name_raises(self):
        with self.assertRaises(UserError):
            self._call('print_report', {
                'report_ref': 'bogus_report_name',
                'ids': [self.partner.id],
            })

    def test_print_no_ids_raises(self):
        with self.assertRaises(UserError):
            self._call('print_report', {
                'report_ref': self.report.id,
                'ids': [],
            })

    def test_print_filename_sanitizes_spaces(self):
        result = self._call('print_report', {
            'report_ref': self.report.id,
            'ids': [self.partner.id],
        })
        self.assertNotIn(' ', result['filename'])
        self.assertIn('MCP_Test_Report', result['filename'])
