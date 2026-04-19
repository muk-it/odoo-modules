import json

from odoo.tests import common


class TestPlayground(common.TransactionCase):

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Key = cls.env['muk_mcp.key']
        cls.Tool = cls.env['muk_mcp.tool']

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _make_user(self, login):
        return self.env['res.users'].create({
            'name': login,
            'login': login,
            'email': f'{login}@example.com',
            'groups_id': [(4, self.env.ref('base.group_user').id)],
        })

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_get_playground_tools_returns_category_and_kind(self):
        tools = self.Tool.get_playground_tools()
        self.assertIsInstance(tools, list)
        for tool in tools:
            self.assertIn('name', tool)
            self.assertIn('description', tool)
            self.assertIn('inputSchema', tool)
            self.assertIsInstance(tool['inputSchema'], dict)
            self.assertIn(tool['category'], ('read', 'write'))
            self.assertIn(tool['kind'], ('db', 'method'))

    def test_get_playground_tools_is_json_serialisable(self):
        tools = self.Tool.get_playground_tools()
        round_tripped = json.loads(json.dumps(tools))
        self.assertEqual(len(round_tripped), len(tools))

    def test_generate_playground_key_returns_plaintext(self):
        user = self._make_user('mcp_user_c')
        result = self.Key.with_user(user).generate_playground_key(
            name='From Test', scope='write',
        )
        self.assertIn('plaintext', result)
        self.assertTrue(result['plaintext'])
        self.assertEqual(result['name'], 'From Test')
        self.assertEqual(result['scope'], 'write')
        self.assertEqual(result['key_prefix'], result['plaintext'][:8])
        record = self.Key.browse(result['id'])
        self.assertEqual(record.user_id, user)
        self.assertEqual(
            record.key_hash, self.Key._hash_key(result['plaintext']),
        )

    def test_generated_key_authenticates(self):
        user = self._make_user('mcp_user_e')
        result = self.Key.with_user(user).generate_playground_key(
            name='Auth Test', scope='read',
        )
        authenticated = self.Key.authenticate(result['plaintext'])
        self.assertTrue(authenticated)
        self.assertEqual(authenticated.user_id, user)

    def test_client_action_registered(self):
        action = self.env.ref('muk_mcp.action_mcp_playground')
        self.assertEqual(action.tag, 'muk_mcp.playground')
        self.assertEqual(action.type, 'ir.actions.client')

    def test_menu_positioned_after_audit_log(self):
        menu = self.env.ref('muk_mcp.menu_mcp_playground')
        self.assertEqual(menu.parent_id, self.env.ref('muk_mcp.menu_mcp_root'))
        self.assertEqual(menu.sequence, 35)
        audit = self.env.ref('muk_mcp.menu_mcp_log')
        self.assertGreater(menu.sequence, audit.sequence)
