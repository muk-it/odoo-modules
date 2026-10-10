from __future__ import annotations

import json

from odoo import models
from odoo.exceptions import AccessError, UserError
from odoo.tests import common, tagged

from odoo.addons.muk_mcp.core import tool as core_tool
from odoo.addons.muk_mcp.core.registry import invalidate_registry_cache
from odoo.addons.muk_mcp.tests.common import cache_tools


def _echo_tool(self, text='hello') -> dict:
    """Echo back the provided text."""
    return {'echo': text}


def _write_tool(self, value=0) -> dict:
    """Echo back the provided value as written."""
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


@tagged('post_install', '-at_install')
class TestMcpDecoratorTool(common.TransactionCase):
    """Covers decorator metadata, registry merging, scope enforcement, and dispatch."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        """Attach the echo and write test tools to the partner model."""
        super().setUpClass()
        cls.tool_model = cls.env['muk_mcp.tool']
        cls.partner_cls = type(cls.env['res.partner'])
        cls.partner_cls._mcp_test_echo = _echo_tool
        cls.partner_cls._mcp_test_write = _write_tool

    @classmethod
    def tearDownClass(cls) -> None:
        """Detach the test tools from the partner model."""
        delattr(cls.partner_cls, '_mcp_test_echo')
        delattr(cls.partner_cls, '_mcp_test_write')
        invalidate_registry_cache(cls.env)
        super().tearDownClass()

    def setUp(self) -> None:
        """Cache the test tool registry."""
        super().setUp()
        self.cached = cache_tools(self.env, TEST_REGISTRY)

    def tearDown(self) -> None:
        """Drop the cached tool registry."""
        invalidate_registry_cache(self.env)
        super().tearDown()

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_decorator_infers_name_and_description_from_function(self):
        @core_tool.mcp_tool()
        def auto_named(self) -> None:
            """First line is the description.

            More detail ignored.
            """
            return

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
        hints = {tool['name']: tool['annotations']['readOnlyHint'] for tool in tools}
        self.assertTrue(hints['mcp_test_echo'])
        self.assertFalse(hints['mcp_test_write'])
        self.assertEqual(
            echo_entry['inputSchema']['properties']['text']['type'],
            'string',
        )

    def test_call_dispatches_decorator_tool(self):
        text, _info = self.tool_model._call(
            'mcp_test_echo',
            {'text': 'world'},
            self.env,
        )
        self.assertEqual(json.loads(text), {'echo': 'world'})

    def test_call_unknown_tool_raises(self):
        with self.assertRaises(UserError):
            self.tool_model._call('does_not_exist', {}, self.env)

    def test_call_bad_arguments_raises_user_error(self):
        with self.assertRaises(UserError):
            self.tool_model._call(
                'mcp_test_echo',
                {'unknown_kwarg': 1},
                self.env,
            )

    def test_call_enforces_read_scope_on_decorator_tool(self):
        with self.assertRaises(AccessError):
            self.tool_model._call(
                'mcp_test_write',
                {'value': 1},
                self.env,
                enforce_scope='read',
            )

    def test_call_allows_write_scope_on_decorator_tool(self):
        text, _info = self.tool_model._call(
            'mcp_test_write',
            {'value': 42},
            self.env,
            enforce_scope='write',
        )
        self.assertEqual(json.loads(text), {'written': 42})

    def test_db_record_shadows_decorator(self):
        db_tool = self.tool_model.create(
            {
                'name': 'mcp_test_echo',
                'description': 'DB override',
                'category': 'read',
                'input_schema': json.dumps(
                    {
                        'type': 'object',
                        'properties': {},
                    },
                ),
                'code': "result = {'echo': 'from_db'}\n",
            },
        )
        tools = self.tool_model.get_tools()
        echo_entries = [t for t in tools if t['name'] == 'mcp_test_echo']
        self.assertEqual(len(echo_entries), 1)
        self.assertEqual(echo_entries[0]['description'], 'DB override')
        text, _info = self.tool_model._call(
            'mcp_test_echo',
            {'text': 'ignored'},
            self.env,
        )
        self.assertEqual(json.loads(text), {'echo': 'from_db'})
        db_tool.unlink()

    def test_call_db_enforces_read_scope(self):
        db_tool = self.tool_model.create(
            {
                'name': 'mcp_test_db_write',
                'description': 'DB write tool',
                'category': 'write',
                'code': "result = {'ok': True}\n",
            },
        )
        with self.assertRaises(AccessError):
            self.tool_model._call(
                'mcp_test_db_write',
                {},
                self.env,
                enforce_scope='read',
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
        def _mcp_scanner_probe(self, value='ping') -> dict:
            """Answer the given value back."""
            return {'pong': value}

        mixin_cls = type(self.env['muk_mcp.mixin'])
        mixin_cls._mcp_scanner_probe = _mcp_scanner_probe
        invalidate_registry_cache(self.env)
        try:
            index = core_tool.get_tool_index(self.env)
            self.assertIn('mcp_scanner_probe', index)
            entry = index['mcp_scanner_probe']
            self.assertEqual(entry['kind'], 'method')
            self.assertEqual(entry['model'], 'muk_mcp.mixin')
            self.assertEqual(entry['method'], '_mcp_scanner_probe')
            self.assertEqual(entry['description'], 'End-to-end scanner probe.')
            text, _info = self.tool_model._call(
                'mcp_scanner_probe',
                {'value': 'pong'},
                self.env,
            )
            self.assertEqual(json.loads(text), {'pong': 'pong'})
        finally:
            delattr(mixin_cls, '_mcp_scanner_probe')
            invalidate_registry_cache(self.env)

    def test_recordset_result_serialized_via_record_encoder(self):
        partner = self.env['res.partner'].create({'name': 'MCP Encoder Test'})

        def _return_recordset(self) -> models.BaseModel:
            """Return the test partner as a recordset."""
            return self.env['res.partner'].browse(partner.id)

        self.partner_cls._mcp_test_record = _return_recordset
        self.cached['mcp_test_record'] = {
            'name': 'mcp_test_record',
            'registry': None,
            'meta': {},
            'kind': 'method',
            'model': 'res.partner',
            'method': '_mcp_test_record',
            'description': 'Return a recordset to exercise serialization.',
            'input_schema': {'type': 'object', 'properties': {}},
            'category': 'read',
        }
        try:
            text, _info = self.tool_model._call('mcp_test_record', {}, self.env)
            payload = json.loads(text)
            self.assertEqual(payload, [[partner.id, 'MCP Encoder Test']])
        finally:
            delattr(self.partner_cls, '_mcp_test_record')
            partner.unlink()
