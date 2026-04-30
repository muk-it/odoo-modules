import json

from odoo.tests import common


class TestConnect(common.TransactionCase):

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['ir.config_parameter'].sudo().set_param(
            'web.base.url', 'https://odoo.example.com',
        )
        cls.wizard = cls.env['muk_mcp.connect'].create({})

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_mcp_url_uses_base_url(self):
        self.assertEqual(self.wizard.mcp_url, 'https://odoo.example.com/mcp')

    def test_mcp_url_strips_trailing_slash(self):
        self.env['ir.config_parameter'].sudo().set_param(
            'web.base.url', 'https://odoo.example.com/',
        )
        wizard = self.env['muk_mcp.connect'].create({})
        self.assertEqual(wizard.mcp_url, 'https://odoo.example.com/mcp')

    def test_action_generate_key_sets_bearer_key(self):
        self.assertFalse(self.wizard.bearer_key)
        self.wizard.action_generate_key()
        self.assertTrue(self.wizard.bearer_key)
        self.assertGreater(len(self.wizard.bearer_key), 16)

    def test_snippets_use_placeholder_without_key(self):
        for snippet in (
            self.wizard.claude_code_cmd,
            self.wizard.claude_desktop_json,
            self.wizard.codex_toml,
            self.wizard.cursor_json,
            self.wizard.opencode_json,
        ):
            self.assertIn('<paste-bearer-key-here>', snippet)

    def test_snippets_embed_bearer_key(self):
        self.wizard.bearer_key = 'sk-test-1234567890'
        self.assertIn('Bearer sk-test-1234567890', self.wizard.claude_code_cmd)
        self.assertIn('Bearer sk-test-1234567890', self.wizard.claude_desktop_json)
        self.assertIn('Bearer sk-test-1234567890', self.wizard.codex_toml)
        self.assertIn('Bearer sk-test-1234567890', self.wizard.cursor_json)
        self.assertIn('Bearer sk-test-1234567890', self.wizard.opencode_json)

    def test_claude_code_command_format(self):
        self.wizard.bearer_key = 'sk-test'
        self.assertIn('claude mcp add --transport http odoo', self.wizard.claude_code_cmd)
        self.assertIn('https://odoo.example.com/mcp', self.wizard.claude_code_cmd)
        self.assertIn('--header "Authorization: Bearer sk-test"', self.wizard.claude_code_cmd)

    def test_claude_desktop_uses_mcp_remote(self):
        self.wizard.bearer_key = 'sk-test'
        payload = json.loads(self.wizard.claude_desktop_json)
        odoo = payload['mcpServers']['odoo']
        self.assertEqual(odoo['command'], 'npx')
        self.assertIn('mcp-remote', odoo['args'])
        self.assertIn('https://odoo.example.com/mcp', odoo['args'])
        self.assertIn('Authorization: Bearer sk-test', odoo['args'])

    def test_codex_toml_format(self):
        self.wizard.bearer_key = 'sk-test'
        toml = self.wizard.codex_toml
        self.assertIn('[mcp_servers.odoo]', toml)
        self.assertIn('url = "https://odoo.example.com/mcp"', toml)
        self.assertIn('headers.Authorization = "Bearer sk-test"', toml)

    def test_cursor_json_format(self):
        self.wizard.bearer_key = 'sk-test'
        payload = json.loads(self.wizard.cursor_json)
        odoo = payload['mcpServers']['odoo']
        self.assertEqual(odoo['url'], 'https://odoo.example.com/mcp')
        self.assertEqual(odoo['headers']['Authorization'], 'Bearer sk-test')

    def test_opencode_json_format(self):
        self.wizard.bearer_key = 'sk-test'
        payload = json.loads(self.wizard.opencode_json)
        odoo = payload['mcp']['odoo']
        self.assertEqual(odoo['type'], 'remote')
        self.assertEqual(odoo['url'], 'https://odoo.example.com/mcp')
        self.assertTrue(odoo['enabled'])
        self.assertEqual(odoo['headers']['Authorization'], 'Bearer sk-test')
