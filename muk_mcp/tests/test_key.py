from __future__ import annotations

from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, new_test_user
from odoo.tools import SQL

from odoo.addons.muk_mcp.tests.common import make_mcp_key


class TestMcpKey(TransactionCase):
    """Cover minting, authenticating and owning MCP keys."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        """Create the key owner and configure the default rate limit."""
        super().setUpClass()
        cls.key_model = cls.env['muk_mcp.key']
        cls.owner = new_test_user(cls.env, login='mcp_key_owner')
        cls.env['ir.config_parameter'].set_int('muk_mcp.rate_limit_requests', 17)
        cls.env['ir.config_parameter'].set_str('web.base.url', 'https://odoo.example/')

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_wizard_reveals_a_working_key_once(self):
        wizard = (
            self.env['muk_mcp.generate_key']
            .with_user(self.owner)
            .create({'name': 'Wizard Key', 'scope': 'read'})
        )
        self.assertEqual(wizard.rate_limit, 17)
        action = wizard.action_make_key()
        self.assertFalse(wizard.exists())
        self.assertEqual(action['res_model'], 'muk_mcp.key.show')
        token = action['context']['default_key']
        dialog = self.env[action['res_model']].with_user(self.owner)
        values = dialog.with_context(action['context']).onchange({}, [], {'key': {}})
        self.assertEqual(values['value']['key'], token)
        key = self.key_model.authenticate(token)
        self.assertEqual(
            (key.name, key.user_id, key.scope, key.rate_limit, key.key_prefix),
            ('Wizard Key', self.owner, 'read', 17, token[:8]),
        )
        key.invalidate_recordset(['last_used'])
        self.assertTrue(key.last_used)
        self.env.flush_all()
        self.env.cr.execute(
            SQL('SELECT * FROM %s WHERE id = %s', SQL.identifier(key._table), key.id),
        )
        self.assertNotIn(token, [str(value) for value in self.env.cr.fetchone()])

    def test_playground_key_carries_its_plaintext(self):
        result = self.key_model.with_user(self.owner).generate_playground_key(
            scope='read',
        )
        key = self.key_model.authenticate(result['plaintext'])
        self.assertEqual(
            result,
            {
                'id': key.id,
                'name': 'Playground',
                'key_prefix': result['plaintext'][:8],
                'scope': 'read',
                'rate_limit': 17,
                'plaintext': result['plaintext'],
            },
        )
        self.assertEqual(key.user_id, self.owner)

    def test_connect_wizard_snippets(self):
        url = 'https://odoo.example/api/mcp'
        values = self.env['muk_mcp.connect'].onchange({}, [], {'mcp_url': {}})['value']
        self.assertEqual(values['mcp_url'], url)
        wizard = self.env['muk_mcp.connect'].with_user(self.owner).create({})
        snippets = (
            'claude_code_cmd',
            'claude_desktop_json',
            'codex_toml',
            'cursor_json',
            'opencode_json',
        )
        for name in snippets:
            self.assertIn('<paste-bearer-key-here>', wizard[name])
        action = wizard.action_generate_key()
        self.assertEqual(action['res_id'], wizard.id)
        key = self.key_model.authenticate(wizard.bearer_key)
        self.assertEqual((key.user_id, key.scope), (self.owner, 'write'))
        for name in snippets:
            with self.subTest(name):
                self.assertIn(url, wizard[name])
                self.assertIn(f'Bearer {wizard.bearer_key}', wizard[name])

    def test_authentication_and_rate_limit(self):
        self.assertEqual(self.key_model.authenticate('no-such-token'), self.key_model)
        _token, limited = make_mcp_key(self.owner, rate_limit=2)
        self.assertEqual(
            [limited._check_rate_limit() for _i in range(3)], [True, True, False]
        )
        _token, unlimited = make_mcp_key(self.owner)
        self.assertTrue(all(unlimited._check_rate_limit() for _i in range(5)))

    def test_users_manage_only_their_own_keys(self):
        _token, key = make_mcp_key(self.owner, rate_limit=5)
        key.with_user(self.owner).rate_limit = 50
        self.assertEqual(key.rate_limit, 50)
        intruder = new_test_user(self.env, login='mcp_key_intruder')
        self.assertFalse(
            self.key_model.with_user(intruder).search([('id', '=', key.id)])
        )
        with self.assertRaises(AccessError):
            key.with_user(intruder).rate_limit = 1
        with self.assertRaises(AccessError):
            intruder.with_user(intruder).write(
                {'mcp_key_ids': [Command.update(key.id, {'user_id': intruder.id})]},
            )
        self.assertEqual((key.user_id, key.rate_limit), (self.owner, 50))
