import inspect
import json

from unittest.mock import patch

from odoo import api
from odoo.service.model import retrying
from odoo.tests import common

from odoo.addons.muk_mcp.controllers import mcp as mcp_controller
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

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tool_model = cls.env['muk_mcp.tool']
        cls.mixin_cls = type(cls.env['muk_mcp.mixin'])
        cls.startClassPatcher(patch.object(
            cls.mixin_cls, '_mcp_test_ctx_probe',
            _mcp_test_ctx_probe, create=True,
        ))
        invalidate_registry_cache(cls.env)
        cls.addClassCleanup(invalidate_registry_cache, cls.env)

    # ----------------------------------------------------------
    # Tests: retry wiring
    # ----------------------------------------------------------

    def test_controller_imports_retrying(self):
        self.assertIs(mcp_controller.retrying, retrying)

    def test_controller_wraps_tools_call_in_retrying(self):
        source = inspect.getsource(
            mcp_controller.MCPController._handle_tools_call
        )
        self.assertIn('retrying(', source)
        self.assertIn('partial(', source)

    # ----------------------------------------------------------
    # Tests: context override
    # ----------------------------------------------------------

    def test_context_override_reaches_python_tool(self):
        text, _info = self.tool_model._call(
            'mcp_test_ctx_probe',
            {'context': {'muk_mcp_probe': 'here'}},
            self.env,
        )
        self.assertEqual(json.loads(text)['flag'], 'here')

    def test_context_override_reaches_db_tool(self):
        tool = self.tool_model.sudo().create({
            'name': 'mcp_test_ctx_probe_db',
            'description': 'Return the probe flag from env.context.',
            'category': 'read',
            'code': "result = {'flag': env.context.get('muk_mcp_probe')}\n",
            'input_schema': json.dumps({'type': 'object', 'properties': {}}),
        })
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
