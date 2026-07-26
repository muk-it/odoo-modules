from __future__ import annotations

from odoo import models
from odoo.tests import common, tagged


@tagged('post_install', '-at_install')
class TestPlayground(common.TransactionCase):
    """Cover playground key generation and menu placement."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.Key = cls.env['muk_mcp.key']
        cls.Tool = cls.env['muk_mcp.tool']

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _make_user(self, login: str) -> models.BaseModel:
        """Create an internal user identified by ``login``."""
        return self.env['res.users'].create(
            {
                'name': login,
                'login': login,
                'email': f'{login}@example.com',
                'group_ids': [(4, self.env.ref('base.group_user').id)],
            },
        )

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_generate_playground_key_returns_plaintext(self):
        user = self._make_user('mcp_user_c')
        result = self.Key.with_user(user).generate_playground_key(
            name='From Test',
            scope='write',
        )
        self.assertIn('plaintext', result)
        self.assertTrue(result['plaintext'])
        self.assertEqual(result['name'], 'From Test')
        self.assertEqual(result['scope'], 'write')
        self.assertEqual(result['key_prefix'], result['plaintext'][:8])
        record = self.Key.browse(result['id'])
        self.assertEqual(record.user_id, user)
        self.assertEqual(
            record.key_hash,
            self.Key._hash_key(result['plaintext']),
        )

    def test_generated_key_authenticates(self):
        user = self._make_user('mcp_user_e')
        result = self.Key.with_user(user).generate_playground_key(
            name='Auth Test',
            scope='read',
        )
        authenticated = self.Key.authenticate(result['plaintext'])
        self.assertTrue(authenticated)
        self.assertEqual(authenticated.user_id, user)

    def test_menu_descends_from_mcp_root(self):
        menu = self.env.ref('muk_mcp.menu_mcp_playground')
        root = self.env.ref('muk_mcp.menu_mcp_root')
        ancestor = menu.parent_id
        while ancestor and ancestor != root:
            ancestor = ancestor.parent_id
        self.assertEqual(
            ancestor, root, 'Playground menu must descend from menu_mcp_root'
        )
