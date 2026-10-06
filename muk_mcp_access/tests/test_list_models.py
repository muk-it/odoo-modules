from __future__ import annotations

import json

from odoo.tests import common, tagged


@tagged('post_install', '-at_install')
class TestMCPAccessListModels(common.TransactionCase):
    """Cover the ``list_models`` filtering against the access allowlist."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.access_model = cls.env['muk_mcp_access.model']
        cls.mixin = cls.env['muk_mcp.mixin']
        cls.tool_model = cls.env['muk_mcp.tool']

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _allow(self, model_name: str, *, read: bool, write: bool) -> None:
        """Add an allowlist entry for a model with the given permissions."""
        self.access_model.create(
            {
                'model_id': self.env['ir.model']._get_id(model_name),
                'allow_read': read,
                'allow_write': write,
            }
        )

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_write_only_model_is_not_listed(self):
        self._allow('res.partner', read=True, write=False)
        self._allow('res.country', read=False, write=True)
        names = [m['model'] for m in self.mixin._mcp_list_models(search='res.')]
        self.assertIn('res.partner', names)
        self.assertNotIn('res.country', names)

    def test_write_only_model_is_not_listed_through_the_tool(self):
        self._allow('res.partner', read=True, write=False)
        self._allow('res.country', read=False, write=True)
        text, _info = self.tool_model._call(
            'list_models',
            {'search': 'res.'},
            self.env,
        )
        names = [m['model'] for m in json.loads(text)]
        self.assertIn('res.partner', names)
        self.assertNotIn('res.country', names)

    def test_read_write_model_is_listed(self):
        self._allow('res.partner', read=True, write=True)
        names = [m['model'] for m in self.mixin._mcp_list_models(search='res.partner')]
        self.assertEqual(names, ['res.partner'])

    def test_allowlisted_model_survives_the_limit(self):
        self._allow('res.partner', read=True, write=False)
        names = [m['model'] for m in self.mixin._mcp_list_models(limit=5)]
        self.assertEqual(names, ['res.partner'])

    def test_default_tool_call_returns_the_allowlist(self):
        self._allow('res.partner', read=True, write=False)
        text, _info = self.tool_model._call('list_models', {}, self.env)
        names = [m['model'] for m in json.loads(text)]
        self.assertEqual(names, ['res.partner'])
