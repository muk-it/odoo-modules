from __future__ import annotations

from odoo.tests import tagged

from odoo.addons.muk_mcp.tests.common import MCPHttpCase


@tagged('post_install', '-at_install')
class TestMcpToolTransaction(MCPHttpCase):
    """Cover the transaction boundary of a failing ``tools/call``."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.mcp_user.group_ids = [
            (4, cls.env.ref('base.group_partner_manager').id),
        ]
        cls.env['muk_mcp.tool'].create(
            {
                'name': 'mcp_partial_write',
                'description': 'Create a partner then raise, for transaction tests.',
                'category': 'write',
                'code': (
                    "env['res.partner'].create({'name': 'MCP Partial Write'})\n"
                    "raise UserError('boom')\n"
                ),
            },
        )

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_failed_tool_call_rolls_back_its_creates(self):
        session_id = self.mcp_handshake()
        body = self.mcp_call_tool('mcp_partial_write', {}, session_id=session_id)
        self.assertTrue(body['result'].get('isError'))
        self.assertEqual(
            self.env['res.partner'].search_count(
                [('name', '=', 'MCP Partial Write')],
            ),
            0,
        )

    def test_failed_update_records_rolls_back_the_write(self):
        partner = self.env['res.partner'].create({'name': 'MCP Rollback'})
        session_id = self.mcp_handshake()
        body = self.mcp_call_tool(
            'update_records',
            {
                'model': 'res.partner',
                'ids': [partner.id],
                'values': {'parent_id': partner.id},
            },
            session_id=session_id,
        )
        self.assertTrue(body['result'].get('isError'))
        self.env.invalidate_all()
        self.assertFalse(partner.parent_id)
