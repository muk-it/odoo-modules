from __future__ import annotations

from odoo.tests import tagged
from odoo.tests.common import new_test_user

from odoo.addons.muk_mcp.tests.common import MCPHttpCase


@tagged('post_install', '-at_install')
class TestMcpPromptAcl(MCPHttpCase):
    """Cover record-rule enforcement on the prompt sandbox environment."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.company_a = cls.env['res.company'].create({'name': 'MCP Prompt A'})
        cls.company_b = cls.env['res.company'].create({'name': 'MCP Prompt B'})
        cls.company_c = cls.env['res.company'].create({'name': 'MCP Prompt C'})
        cls.restricted_user = new_test_user(
            cls.env,
            login='mcp_prompt_restricted',
            groups='base.group_user',
            company_id=cls.company_a.id,
            company_ids=[(6, 0, [cls.company_a.id, cls.company_b.id])],
        )
        cls.restricted_token, cls.restricted_key = cls.make_mcp_key(
            cls.restricted_user,
        )
        cls.partner_ids = (
            cls.env['res.partner']
            .create(
                [
                    {'name': 'MCP Prompt ACL A', 'company_id': cls.company_a.id},
                    {'name': 'MCP Prompt ACL B', 'company_id': cls.company_b.id},
                    {'name': 'MCP Prompt ACL C', 'company_id': cls.company_c.id},
                ],
            )
            .ids
        )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def get_prompt_text(
        self,
        name: str,
        token: str | None = None,
    ) -> str:
        """Call ``prompts/get`` over HTTP and return the first message's text."""
        session_id = self.mcp_handshake(token=token)
        body = self.mcp_json(
            {
                'jsonrpc': '2.0',
                'id': 7,
                'method': 'prompts/get',
                'params': {'name': name},
            },
            token=token,
            session_id=session_id,
        )
        return body['result']['messages'][0]['content']['text']

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_prompt_body_runs_without_superuser(self):
        self.env['muk_mcp.prompt'].create(
            {
                'name': 'mcp_su_probe',
                'title': 'Probe',
                'description': 'Probe.',
                'body': "result = 'su=%s' % env.su\n",
            },
        )
        self.assertEqual(self.get_prompt_text('mcp_su_probe'), 'su=False')

    def test_prompt_body_honours_the_multi_company_rule(self):
        self.env['muk_mcp.prompt'].create(
            {
                'name': 'mcp_company_probe',
                'title': 'Probe',
                'description': 'Probe.',
                'body': (
                    "result = str(env['res.partner'].search_count("
                    "[('id', 'in', %s)]))\n" % self.partner_ids
                ),
            },
        )
        self.assertEqual(
            self.get_prompt_text(
                'mcp_company_probe',
                token=self.restricted_token,
            ),
            '2',
        )
