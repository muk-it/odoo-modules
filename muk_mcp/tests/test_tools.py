import json

from odoo.tests import common


class TestMcpTool(common.TransactionCase):

    # ----------------------------------------------------------
    # Defaults
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tool_model = cls.env['muk_mcp.tool']

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_get_tools_returns_active(self):
        tools = self.tool_model.get_tools()
        self.assertIsInstance(tools, list)
        self.assertTrue(len(tools) > 0)
        for tool in tools:
            self.assertIn('name', tool)
            self.assertIn('description', tool)
            self.assertIn('inputSchema', tool)

    def test_list_models_handler(self):
        tool = self.tool_model.search([
            ('name', '=', 'list_models'),
        ], limit=1)
        self.assertTrue(tool, 'list_models tool should exist')
        result_str = tool._run(
            {'search': 'res.partner', 'limit': 10}, self.env
        )
        result = json.loads(result_str)
        self.assertIsInstance(result, list)
        model_names = [m['model'] for m in result]
        self.assertIn('res.partner', model_names)

    def test_get_model_schema_handler(self):
        tool = self.tool_model.search([
            ('name', '=', 'get_model_schema'),
        ], limit=1)
        self.assertTrue(tool, 'get_model_schema tool should exist')
        result_str = tool._run(
            {'model': 'res.partner'}, self.env
        )
        result = json.loads(result_str)
        self.assertIn('name', result)
        self.assertIn('email', result)
        self.assertEqual(result['name']['type'], 'char')

    def test_search_read_handler(self):
        tool = self.tool_model.search([
            ('name', '=', 'search_read'),
        ], limit=1)
        self.assertTrue(tool, 'search_read tool should exist')
        result_str = tool._run({
            'model': 'res.partner',
            'domain': [['is_company', '=', True]],
            'fields': ['name', 'email'],
            'limit': 5,
        }, self.env)
        result = json.loads(result_str)
        self.assertIsInstance(result, list)

    def test_create_and_unlink_handler(self):
        create_tool = self.tool_model.search([
            ('name', '=', 'create_record'),
        ], limit=1)
        self.assertTrue(create_tool, 'create_record tool should exist')
        result_str = create_tool._run({
            'model': 'res.partner.category',
            'values': {'name': 'MCP Test Category'},
        }, self.env)
        result = json.loads(result_str)
        self.assertIn('id', result)
        record_id = result['id']
        unlink_tool = self.tool_model.search([
            ('name', '=', 'delete_record'),
        ], limit=1)
        result_str = unlink_tool._run({
            'model': 'res.partner.category',
            'ids': [record_id],
        }, self.env)
        result = json.loads(result_str)
        self.assertTrue(result['success'])

    def test_search_count_handler(self):
        tool = self.tool_model.search([
            ('name', '=', 'search_count'),
        ], limit=1)
        self.assertTrue(tool, 'search_count tool should exist')
        result_str = tool._run({
            'model': 'res.partner',
            'domain': [],
        }, self.env)
        result = json.loads(result_str)
        self.assertIn('count', result)
        self.assertGreater(result['count'], 0)

    def test_invalid_model_returns_error(self):
        tool = self.tool_model.search([
            ('name', '=', 'search_read'),
        ], limit=1)
        result_str = tool._run({
            'model': 'nonexistent.model',
            'domain': [],
        }, self.env)
        result = json.loads(result_str)
        self.assertIn('error', result)

    def test_private_method_blocked(self):
        tool = self.tool_model.search([
            ('name', '=', 'execute_method'),
        ], limit=1)
        result_str = tool._run({
            'model': 'res.partner',
            'method': '_check_company',
        }, self.env)
        result = json.loads(result_str)
        self.assertIn('error', result)
        self.assertIn('Private methods', result['error'])
