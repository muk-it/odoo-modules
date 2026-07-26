from __future__ import annotations

import json

from odoo import api
from odoo.tests import common

from odoo.addons.muk_mcp.core.tool import invalidate_registry_cache, mcp_tool


@api.model
@mcp_tool(
    name='mcp_test_ctx_probe',
    description='Return the probe flag from env.context.',
    input_schema={'type': 'object', 'properties': {}},
    category='read',
)
def _mcp_test_ctx_probe(self):
    return {'flag': self.env.context.get('muk_mcp_probe')}


class TestMcpDispatch(common.TransactionCase):
    """Covers context override propagation through the tool dispatch path."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.tool_model = cls.env['muk_mcp.tool']
        cls.mixin_cls = type(cls.env['muk_mcp.mixin'])
        cls.mixin_cls._mcp_test_ctx_probe = _mcp_test_ctx_probe
        invalidate_registry_cache(cls.env)

    @classmethod
    def tearDownClass(cls) -> None:
        delattr(cls.mixin_cls, '_mcp_test_ctx_probe')
        invalidate_registry_cache(cls.env)
        super().tearDownClass()

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_context_override_reaches_python_tool(self):
        text, _info = self.tool_model._call(
            'mcp_test_ctx_probe',
            {'context': {'muk_mcp_probe': 'here'}},
            self.env,
        )
        self.assertEqual(json.loads(text)['flag'], 'here')

    def test_context_override_reaches_db_tool(self):
        tool = self.tool_model.sudo().create(
            {
                'name': 'mcp_test_ctx_probe_db',
                'description': 'Return the probe flag from env.context.',
                'category': 'read',
                'code': "result = {'flag': env.context.get('muk_mcp_probe')}\n",
                'input_schema': json.dumps({'type': 'object', 'properties': {}}),
            },
        )
        try:
            text, _info = self.tool_model._call(
                'mcp_test_ctx_probe_db',
                {'context': {'muk_mcp_probe': 'db_here'}},
                self.env,
            )
            self.assertEqual(json.loads(text)['flag'], 'db_here')
        finally:
            tool.unlink()

    def test_context_override_does_not_mutate_caller_env(self):
        self.tool_model._call(
            'mcp_test_ctx_probe',
            {'context': {'muk_mcp_probe': 'temp'}},
            self.env,
        )
        self.assertIsNone(self.env.context.get('muk_mcp_probe'))

    def test_context_override_ignored_when_not_dict(self):
        text, _info = self.tool_model._call(
            'mcp_test_ctx_probe',
            {'context': 'not-a-dict'},
            self.env,
        )
        self.assertIsNone(json.loads(text)['flag'])
