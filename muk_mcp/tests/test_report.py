from __future__ import annotations

import base64

from odoo.exceptions import UserError

from odoo.addons.muk_mcp.tests.common import MCPToolCase


class TestMcpPrintReport(MCPToolCase):
    """Cover ``print_report`` and the ways a report can be referenced."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        """Create a text and an HTML report on partners, the first with an xmlid."""
        super().setUpClass()
        cls.env['ir.ui.view'].create(
            {
                'type': 'qweb',
                'key': 'muk_mcp.test_report',
                'arch': (
                    '<t t-name="muk_mcp.test_report">'
                    '<t t-foreach="docs" t-as="doc"><t t-out="doc.name"/>|</t>'
                    '</t>'
                ),
            },
        )
        cls.report, cls.html_report = cls.env['ir.actions.report'].create(
            [
                {
                    'name': name,
                    'report_name': 'muk_mcp.test_report',
                    'report_type': report_type,
                    'model': 'res.partner',
                }
                for name, report_type in (
                    ('MCP Test Report', 'qweb-text'),
                    ('MCP Web Report', 'qweb-html'),
                )
            ],
        )
        cls.env['ir.model.data'].create(
            {
                'name': 'test_action_report',
                'module': 'muk_mcp',
                'model': 'ir.actions.report',
                'res_id': cls.report.id,
            },
        )
        cls.partner = cls.env['res.partner'].create({'name': 'MCP Print Target'})

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_report_is_rendered_by_any_reference(self):
        for report_ref, filename, mimetype in (
            (self.report.id, 'MCP_Test_Report.txt', 'text/plain'),
            ('muk_mcp.test_action_report', 'MCP_Test_Report.txt', 'text/plain'),
            (' muk_mcp.test_report ', 'MCP_Test_Report.txt', 'text/plain'),
            (self.html_report.id, 'MCP_Web_Report.html', 'text/html'),
        ):
            with self.subTest(report_ref):
                result = self.call_tool(
                    'print_report',
                    {'report_ref': report_ref, 'ids': [self.partner.id]},
                )
                self.assertEqual(
                    (result['filename'], result['mimetype']), (filename, mimetype)
                )
                self.assertIn(
                    'MCP Print Target|',
                    base64.b64decode(result['content_base64']).decode(),
                )

    def test_unknown_reports_and_missing_ids_raise(self):
        for report_ref, ids in (
            ('muk_mcp.no_such_report', [self.partner.id]),
            ('no_such_report', [self.partner.id]),
            (self.report.id, []),
        ):
            with self.subTest(report_ref), self.assertRaises(UserError):
                self.call_tool('print_report', {'report_ref': report_ref, 'ids': ids})
