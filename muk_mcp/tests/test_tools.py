import json

from odoo.exceptions import UserError
from odoo.tests import common


class TestMcpTool(common.TransactionCase):

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tool_model = cls.env['muk_mcp.tool']

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _call(self, name, arguments):
        text, _info = self.tool_model._call(name, arguments, self.env)
        return json.loads(text)

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_get_tools_returns_active(self):
        tools = self.tool_model.get_tools()
        self.assertIsInstance(tools, list)
        self.assertTrue(len(tools) > 0)
        for entry in tools:
            self.assertIn('name', entry)
            self.assertIn('description', entry)
            self.assertIn('inputSchema', entry)

    def test_list_models_handler(self):
        result = self._call('list_models', {'search': 'res.partner', 'limit': 10})
        self.assertIsInstance(result, list)
        self.assertIn('res.partner', [m['model'] for m in result])

    def test_list_modules_handler(self):
        result = self._call('list_modules', {'search': 'base'})
        self.assertIsInstance(result, list)
        self.assertTrue(any(m['name'] == 'base' for m in result))

    def test_describe_model_handler(self):
        result = self._call('describe_model', {'model': 'res.partner'})
        self.assertIn('name', result)
        self.assertIn('email', result)
        self.assertEqual(result['name']['type'], 'char')

    def test_search_read_handler(self):
        result = self._call('search_read', {
            'model': 'res.partner',
            'domain': [['is_company', '=', True]],
            'fields': ['name', 'email'],
            'limit': 5,
        })
        self.assertIsInstance(result, list)

    def test_search_count_handler(self):
        result = self._call('search_count', {'model': 'res.partner', 'domain': []})
        self.assertIn('count', result)
        self.assertGreater(result['count'], 0)

    def test_create_and_delete_handler(self):
        created = self._call('create_records', {
            'model': 'res.partner.category',
            'values': {'name': 'MCP Test Category'},
        })
        self.assertIn('id', created)
        deleted = self._call('delete_records', {
            'model': 'res.partner.category',
            'ids': [created['id']],
        })
        self.assertTrue(deleted['success'])

    def test_update_handler(self):
        record = self.env['res.partner.category'].create({'name': 'MCP Update'})
        try:
            result = self._call('update_records', {
                'model': 'res.partner.category',
                'ids': [record.id],
                'values': {'name': 'MCP Updated'},
            })
            self.assertTrue(result['success'])
            self.assertEqual(record.name, 'MCP Updated')
        finally:
            record.unlink()

    def test_read_handler(self):
        partner = self.env['res.partner'].search([], limit=1)
        self.assertTrue(partner)
        result = self._call('read_records', {
            'model': 'res.partner',
            'ids': [partner.id],
            'fields': ['name'],
        })
        self.assertEqual(result[0]['id'], partner.id)

    def test_whoami_handler(self):
        result = self._call('whoami', {})
        self.assertIn('uid', result)
        self.assertEqual(result['uid'], self.env.uid)
        self.assertIn('company_id', result)
        self.assertIn('groups', result)

    def test_get_access_rights_handler(self):
        result = self._call('get_access_rights', {'model': 'res.partner'})
        self.assertEqual(result['model'], 'res.partner')
        self.assertIn('current_user_rights', result)
        self.assertIn('read', result['current_user_rights'])

    def test_read_group_handler(self):
        result = self._call('read_group', {
            'model': 'res.partner',
            'domain': [],
            'fields': ['is_company'],
            'groupby': ['is_company'],
        })
        self.assertIsInstance(result, list)

    def test_invalid_model_raises(self):
        with self.assertRaises(UserError):
            self._call('search_read', {
                'model': 'nonexistent.model',
                'domain': [],
            })

    def test_private_method_blocked(self):
        with self.assertRaisesRegex(UserError, 'Private methods'):
            self._call('call_method', {
                'model': 'res.partner',
                'method': '_check_company',
            })

    def test_method_not_found(self):
        with self.assertRaisesRegex(UserError, 'does not exist'):
            self._call('call_method', {
                'model': 'res.partner',
                'method': 'totally_nonexistent_method_xyz',
            })

    def test_empty_ids_raises(self):
        with self.assertRaises(UserError):
            self._call('delete_records', {
                'model': 'res.partner.category',
                'ids': [],
            })

    def test_read_group_without_groupby_raises(self):
        with self.assertRaises(UserError):
            self._call('read_group', {
                'model': 'res.partner',
                'fields': ['is_company'],
                'groupby': [],
            })

    def test_tool_result_contains_id_for_create(self):
        created = self._call('create_records', {
            'model': 'res.partner.category',
            'values': {'name': 'MCP ID Test'},
        })
        self.assertIn('id', created)
        self.assertIsInstance(created['id'], int)
        self.env['res.partner.category'].browse(created['id']).unlink()

    def test_context_override_threads_through(self):
        archived = self.env['res.partner'].create({
            'name': 'MCP Archived Partner',
            'active': False,
        })
        try:
            active_default = self._call('search_read', {
                'model': 'res.partner',
                'domain': [['id', '=', archived.id]],
                'fields': ['id'],
            })
            self.assertEqual(active_default, [])
            with_override = self._call('search_read', {
                'model': 'res.partner',
                'domain': [['id', '=', archived.id]],
                'fields': ['id'],
                'context': {'active_test': False},
            })
            self.assertEqual(len(with_override), 1)
            self.assertEqual(with_override[0]['id'], archived.id)
        finally:
            archived.unlink()

    def test_mail_tools_still_resolve_via_db(self):
        tools = self.tool_model.get_tools()
        names = {t['name'] for t in tools}
        self.assertIn('get_messages', names)
        self.assertIn('post_message', names)
        db_records = self.tool_model.search([
            ('name', 'in', ['get_messages', 'post_message']),
        ])
        self.assertEqual(len(db_records), 2)
