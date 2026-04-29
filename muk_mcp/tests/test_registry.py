import json

from odoo.tests import common

from odoo.addons.muk_mcp.core import tool as core_tool


class TestMcpRegistryFilter(common.TransactionCase):

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tool_model = cls.env['muk_mcp.tool']

    def setUp(self):
        super().setUp()
        self.env.registry._muk_mcp_method_cache = {
            'tool_unscoped': {
                'kind': 'method',
                'model': 'res.partner',
                'method': '_x',
                'description': 'Visible to all callers.',
                'input_schema': {'type': 'object', 'properties': {}},
                'category': 'read',
                'registry': None,
            },
            'tool_mcp_only': {
                'kind': 'method',
                'model': 'res.partner',
                'method': '_x',
                'description': 'MCP only.',
                'input_schema': {'type': 'object', 'properties': {}},
                'category': 'read',
                'registry': 'mcp',
            },
            'tool_ai_only': {
                'kind': 'method',
                'model': 'res.partner',
                'method': '_x',
                'description': 'AI only.',
                'input_schema': {'type': 'object', 'properties': {}},
                'category': 'read',
                'registry': 'ai',
            },
            'tool_multi': {
                'kind': 'method',
                'model': 'res.partner',
                'method': '_x',
                'description': 'Shared between mcp and cron.',
                'input_schema': {'type': 'object', 'properties': {}},
                'category': 'read',
                'registry': 'mcp,cron',
            },
        }

    def tearDown(self):
        core_tool.invalidate_registry_cache(self.env)
        super().tearDown()

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _decorate(self, **kwargs):
        @core_tool.mcp_tool(**kwargs)
        def handler(self):
            return None
        return handler.__mcp_tool__

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_decorator_default_registry_is_none(self):
        meta = self._decorate(name='plain', description='Plain')
        self.assertIsNone(meta['registry'])

    def test_decorator_records_registry(self):
        meta = self._decorate(
            name='scoped', description='Scoped', registry='ai'
        )
        self.assertEqual(meta['registry'], 'ai')

    def test_filter_none_returns_everything(self):
        names = set(core_tool.get_tool_index(self.env).keys())
        self.assertIn('tool_unscoped', names)
        self.assertIn('tool_mcp_only', names)
        self.assertIn('tool_ai_only', names)
        self.assertIn('tool_multi', names)

    def test_filter_mcp_hides_ai_only(self):
        names = set(core_tool.get_tool_index(
            self.env, registry='mcp',
        ).keys())
        self.assertIn('tool_unscoped', names)
        self.assertIn('tool_mcp_only', names)
        self.assertIn('tool_multi', names)
        self.assertNotIn('tool_ai_only', names)

    def test_filter_ai_hides_mcp_only(self):
        names = set(core_tool.get_tool_index(
            self.env, registry='ai',
        ).keys())
        self.assertIn('tool_unscoped', names)
        self.assertIn('tool_ai_only', names)
        self.assertNotIn('tool_mcp_only', names)
        self.assertNotIn('tool_multi', names)

    def test_filter_matches_csv_registry(self):
        names = set(core_tool.get_tool_index(
            self.env, registry='cron',
        ).keys())
        self.assertIn('tool_unscoped', names)
        self.assertIn('tool_multi', names)
        self.assertNotIn('tool_mcp_only', names)
        self.assertNotIn('tool_ai_only', names)

    def test_filter_unknown_registry_only_shows_unscoped(self):
        names = set(core_tool.get_tool_index(
            self.env, registry='ghost',
        ).keys())
        self.assertIn('tool_unscoped', names)
        self.assertNotIn('tool_mcp_only', names)
        self.assertNotIn('tool_ai_only', names)
        self.assertNotIn('tool_multi', names)

    def test_get_tools_forwards_registry(self):
        mcp_tools = {t['name'] for t in self.tool_model.get_tools(
            registry='mcp',
        )}
        self.assertIn('tool_unscoped', mcp_tools)
        self.assertIn('tool_mcp_only', mcp_tools)
        self.assertNotIn('tool_ai_only', mcp_tools)

    def test_db_record_registry_default_is_none(self):
        record = self.tool_model.create({
            'name': 'mcp_test_db_registry_default',
            'description': 'Default',
            'category': 'read',
            'code': "result = {'ok': True}\n",
        })
        entry = core_tool.get_tool_index(self.env).get(record.name)
        self.assertIsNotNone(entry)
        self.assertFalse(entry.get('registry'))
        record.unlink()

    def test_db_record_registry_mcp_respected(self):
        record = self.tool_model.create({
            'name': 'mcp_test_db_registry_mcp',
            'description': 'MCP only',
            'category': 'read',
            'registry': 'mcp',
            'code': "result = {'ok': True}\n",
        })
        mcp_names = {
            t['name'] for t in self.tool_model.get_tools(registry='mcp')
        }
        self.assertIn(record.name, mcp_names)
        ai_names = {
            t['name'] for t in self.tool_model.get_tools(registry='ai')
        }
        self.assertNotIn(record.name, ai_names)
        record.unlink()
