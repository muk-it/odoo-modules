import json

from unittest.mock import patch

from odoo.exceptions import AccessError, UserError
from odoo.tests import common

from odoo.addons.muk_mcp.core import tool as core_tool


def _echo_tool(self, text='hello'):
    return {'echo': text}


def _write_tool(self, value=0):
    return {'written': value}


TEST_REGISTRY = {
    'mcp_test_echo': {
        'kind': 'method',
        'model': 'res.partner',
        'method': '_mcp_test_echo',
        'description': 'Echo back the provided text.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'text': {'type': 'string'},
            },
        },
        'category': 'read',
    },
    'mcp_test_write': {
        'kind': 'method',
        'model': 'res.partner',
        'method': '_mcp_test_write',
        'description': 'Write-category tool for scope tests.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'value': {'type': 'integer'},
            },
        },
        'category': 'write',
    },
}


class TestMcpDecoratorTool(common.TransactionCase):

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tool_model = cls.env['muk_mcp.tool']
        cls.partner_cls = type(cls.env['res.partner'])
        cls.startClassPatcher(patch.object(
            cls.partner_cls, '_mcp_test_echo', _echo_tool, create=True,
        ))
        cls.startClassPatcher(patch.object(
            cls.partner_cls, '_mcp_test_write', _write_tool, create=True,
        ))
        cls.addClassCleanup(core_tool.invalidate_registry_cache, cls.env)

    def setUp(self):
        super().setUp()
        self.env.registry._muk_mcp_method_cache = dict(TEST_REGISTRY)

    def tearDown(self):
        core_tool.invalidate_registry_cache(self.env)
        super().tearDown()

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_decorator_stamps_metadata(self):
        @core_tool.mcp_tool(
            name='dummy',
            description='Does nothing.',
            input_schema={'type': 'object', 'properties': {}},
            category='write',
        )
        def handler(self, **kw):
            return None

        self.assertEqual(handler.__mcp_tool__['name'], 'dummy')
        self.assertEqual(handler.__mcp_tool__['description'], 'Does nothing.')
        self.assertEqual(handler.__mcp_tool__['category'], 'write')

    def test_decorator_infers_name_and_description_from_function(self):
        @core_tool.mcp_tool()
        def auto_named(self):
            """First line is the description.

            More detail ignored.
            """
            return None

        self.assertEqual(auto_named.__mcp_tool__['name'], 'auto_named')
        self.assertEqual(
            auto_named.__mcp_tool__['description'],
            'First line is the description.',
        )
        self.assertEqual(auto_named.__mcp_tool__['category'], 'read')

    def test_get_tools_merges_decorator_entries(self):
        tools = self.tool_model.get_tools()
        names = [entry['name'] for entry in tools]
        self.assertIn('mcp_test_echo', names)
        self.assertIn('mcp_test_write', names)
        echo_entry = next(t for t in tools if t['name'] == 'mcp_test_echo')
        self.assertEqual(echo_entry['description'], 'Echo back the provided text.')
        self.assertEqual(
            echo_entry['inputSchema']['properties']['text']['type'], 'string',
        )

    def test_call_dispatches_decorator_tool(self):
        text, _info = self.tool_model._call(
            'mcp_test_echo', {'text': 'world'}, self.env,
        )
        self.assertEqual(json.loads(text), {'echo': 'world'})

    def test_call_unknown_tool_raises(self):
        with self.assertRaises(UserError):
            self.tool_model._call('does_not_exist', {}, self.env)

    def test_call_bad_arguments_raises_user_error(self):
        with self.assertRaises(UserError):
            self.tool_model._call(
                'mcp_test_echo', {'unknown_kwarg': 1}, self.env,
            )

    def test_call_enforces_read_scope_on_decorator_tool(self):
        with self.assertRaises(AccessError):
            self.tool_model._call(
                'mcp_test_write', {'value': 1}, self.env, enforce_scope='read',
            )

    def test_call_allows_write_scope_on_decorator_tool(self):
        text, _info = self.tool_model._call(
            'mcp_test_write', {'value': 42}, self.env, enforce_scope='write',
        )
        self.assertEqual(json.loads(text), {'written': 42})

    def test_db_record_shadows_decorator(self):
        db_tool = self.tool_model.create({
            'name': 'mcp_test_echo',
            'description': 'DB override',
            'category': 'read',
            'input_schema': json.dumps({
                'type': 'object',
                'properties': {},
            }),
            'code': "result = {'echo': 'from_db'}\n",
        })
        tools = self.tool_model.get_tools()
        echo_entries = [t for t in tools if t['name'] == 'mcp_test_echo']
        self.assertEqual(len(echo_entries), 1)
        self.assertEqual(echo_entries[0]['description'], 'DB override')
        text, _info = self.tool_model._call(
            'mcp_test_echo', {'text': 'ignored'}, self.env,
        )
        self.assertEqual(json.loads(text), {'echo': 'from_db'})
        db_tool.unlink()

    def test_call_db_enforces_read_scope(self):
        db_tool = self.tool_model.create({
            'name': 'mcp_test_db_write',
            'description': 'DB write tool',
            'category': 'write',
            'code': "result = {'ok': True}\n",
        })
        with self.assertRaises(AccessError):
            self.tool_model._call(
                'mcp_test_db_write', {}, self.env, enforce_scope='read',
            )
        db_tool.unlink()

    def test_scanner_finds_decorated_method_on_live_registry(self):
        @core_tool.mcp_tool(
            name='mcp_scanner_probe',
            description='End-to-end scanner probe.',
            input_schema={
                'type': 'object',
                'properties': {'value': {'type': 'string'}},
            },
            category='read',
        )
        def _mcp_scanner_probe(self, value='ping'):
            return {'pong': value}

        mixin_cls = type(self.env['muk_mcp.mixin'])
        self.startPatcher(patch.object(
            mixin_cls, '_mcp_scanner_probe', _mcp_scanner_probe, create=True,
        ))
        core_tool.invalidate_registry_cache(self.env)
        self.addCleanup(core_tool.invalidate_registry_cache, self.env)
        index = core_tool.get_tool_index(self.env)
        self.assertIn('mcp_scanner_probe', index)
        entry = index['mcp_scanner_probe']
        self.assertEqual(entry['kind'], 'method')
        self.assertEqual(entry['model'], 'muk_mcp.mixin')
        self.assertEqual(entry['method'], '_mcp_scanner_probe')
        self.assertEqual(entry['description'], 'End-to-end scanner probe.')
        text, _info = self.tool_model._call(
            'mcp_scanner_probe', {'value': 'pong'}, self.env,
        )
        self.assertEqual(json.loads(text), {'pong': 'pong'})

    def test_recordset_result_serialized_via_record_encoder(self):
        partner = self.env['res.partner'].create({'name': 'MCP Encoder Test'})
        self.addCleanup(partner.unlink)

        def _return_recordset(self):
            return self.env['res.partner'].browse(partner.id)

        self.startPatcher(patch.object(
            self.partner_cls, '_mcp_test_record',
            _return_recordset, create=True,
        ))
        self.env.registry._muk_mcp_method_cache['mcp_test_record'] = {
            'kind': 'method',
            'model': 'res.partner',
            'method': '_mcp_test_record',
            'description': 'Return a recordset to exercise serialization.',
            'input_schema': {'type': 'object', 'properties': {}},
            'category': 'read',
        }
        text, _info = self.tool_model._call('mcp_test_record', {}, self.env)
        payload = json.loads(text)
        self.assertEqual(payload, [[partner.id, 'MCP Encoder Test']])
