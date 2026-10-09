from __future__ import annotations

import json
from typing import Any

from odoo import models
from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase

from odoo.addons.muk_mcp.core.registry import invalidate_registry_cache
from odoo.addons.muk_mcp.core.tool import mcp_tool


@mcp_tool(
    name='mcp_access_nested_write',
    description='Re-enter a read tool from inside a write tool.',
    input_schema={
        'type': 'object',
        'properties': {'model': {'type': 'string'}},
        'required': ['model'],
    },
    category='write',
)
def _nested_write_tool(self, model: str) -> dict[str, Any]:
    """Call a read tool, then resolve a model under the outer write category."""
    self.env['muk_mcp.tool']._call('list_models', {'limit': 1}, self.env)
    self._resolve_model(model)
    return {'resolved': model}


class TestMCPAccessEnforcement(TransactionCase):
    """Cover the tool-category enforcement path from ``_call`` to ``_resolve_model``."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        """Resolve the models and register the nested write probe tool."""
        super().setUpClass()
        cls.access_model = cls.env['muk_mcp_access.model']
        cls.tool_model = cls.env['muk_mcp.tool']
        cls.mixin = cls.env['muk_mcp.mixin']
        cls.mixin_cls = type(cls.env['muk_mcp.mixin'])
        cls.mixin_cls._mcp_access_nested_write = _nested_write_tool
        invalidate_registry_cache(cls.env)
        cls.addClassCleanup(invalidate_registry_cache, cls.env)
        cls.addClassCleanup(delattr, cls.mixin_cls, '_mcp_access_nested_write')

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _allow(
        self,
        model_name: str,
        *,
        read: bool = True,
        write: bool = False,
    ) -> None:
        """Add an allowlist entry for a model with the given permissions."""
        self.access_model.create(
            {
                'model_id': self.env['ir.model']._get_id(model_name),
                'allow_read': read,
                'allow_write': write,
            }
        )

    def _call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        """Invoke an MCP tool the way a cron or direct ORM caller does, with no request bound."""
        text, _info = self.tool_model._call(name, arguments, self.env)
        return json.loads(text) if isinstance(text, str) else text

    def _new_partner(self, name: str) -> models.BaseModel:
        """Create a plain partner to act on through the write tools."""
        return self.env['res.partner'].create({'name': name})

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_write_tools_follow_the_write_permission(self):
        self._allow('res.partner', read=True, write=False)
        entry = self.access_model.search([('model_name', '=', 'res.partner')])
        partners = self.env['res.partner']
        cases = (
            (
                'create_records',
                lambda p: {'model': 'res.partner', 'values': {'name': 'MCP_CREATED'}},
                lambda p: partners.search_count([('name', '=', 'MCP_CREATED')]),
            ),
            (
                'update_records',
                lambda p: {
                    'model': 'res.partner',
                    'ids': [p.id],
                    'values': {'function': 'changed'},
                },
                lambda p: p.function == 'changed',
            ),
            (
                'delete_records',
                lambda p: {'model': 'res.partner', 'ids': [p.id]},
                lambda p: not p.exists(),
            ),
            (
                'call_method',
                lambda p: {
                    'model': 'res.partner',
                    'method': 'write',
                    'ids': [p.id],
                    'args': '[{"function": "changed"}]',
                },
                lambda p: p.function == 'changed',
            ),
        )
        for write in (False, True):
            entry.allow_write = write
            for name, arguments, done in cases:
                partner = self._new_partner('MCP_TARGET')
                with self.subTest(tool=name, write=write):
                    if write:
                        self._call_tool(name, arguments(partner))
                    else:
                        with self.assertRaises(AccessError):
                            self._call_tool(name, arguments(partner))
                    self.assertEqual(bool(done(partner)), write)

    def test_nested_read_tool_does_not_downgrade_outer_write_tool(self):
        self._allow('res.partner', read=True, write=False)
        with self.assertRaises(AccessError):
            self._call_tool(
                'mcp_access_nested_write',
                {'model': 'res.partner'},
            )

    def test_nested_read_tool_keeps_outer_write_tool_working(self):
        self._allow('res.partner', read=True, write=True)
        result = self._call_tool(
            'mcp_access_nested_write',
            {'model': 'res.partner'},
        )
        self.assertEqual(result, {'resolved': 'res.partner'})

    def test_context_override_cannot_downgrade_write_tool(self):
        self._allow('res.partner', read=True, write=False)
        with self.assertRaises(AccessError):
            self._call_tool(
                'create_records',
                {
                    'model': 'res.partner',
                    'values': {'name': 'MCP_CONTEXT_DOWNGRADE'},
                    'context': {'mcp_tool_category': 'read'},
                },
            )
        self.assertFalse(
            self.env['res.partner'].search(
                [('name', '=', 'MCP_CONTEXT_DOWNGRADE')],
            ),
        )

    def test_context_override_is_still_applied_to_the_tool(self):
        self._allow('res.partner', read=True, write=True)
        result = self._call_tool(
            'create_records',
            {
                'model': 'res.partner',
                'values': {'name': 'MCP_CONTEXT_KEPT'},
                'context': {'default_function': 'from_context'},
            },
        )
        self.assertEqual(
            self.env['res.partner'].browse(result['id']).function,
            'from_context',
        )

    def test_read_and_write_permissions_are_independent(self):
        self._allow('res.partner')
        entry = self.access_model.search([('model_name', '=', 'res.partner')])
        calls = (
            ('search_read', {'model': 'res.partner', 'fields': ['name'], 'limit': 1}),
            ('create_records', {'model': 'res.partner', 'values': {'name': 'MCP_X'}}),
        )
        for read, write in ((True, False), (False, True)):
            entry.write({'allow_read': read, 'allow_write': write})
            for (name, arguments), allowed in zip(calls, (read, write), strict=True):
                with self.subTest(tool=name, read=read, write=write):
                    if allowed:
                        self.assertTrue(self._call_tool(name, arguments))
                    else:
                        with self.assertRaises(AccessError):
                            self._call_tool(name, arguments)

    def test_unlisted_model_denied_for_sudo_and_admin(self):
        self._allow('res.partner')
        admin = self.env.ref('base.user_admin')
        with self.assertRaises(AccessError):
            self.mixin.sudo()._resolve_model('res.country')
        with self.assertRaises(AccessError):
            self.mixin.with_user(admin)._resolve_model('res.country')

    def test_removing_every_entry_reopens_the_whole_registry(self):
        for remove in ('unlink', 'action_archive'):
            entry = self.access_model.create(
                {'model_id': self.env['ir.model']._get_id('res.partner')},
            )
            with self.subTest(remove=remove):
                with self.assertRaises(AccessError):
                    self.mixin._resolve_model('res.country')
                getattr(entry, remove)()
                self.assertFalse(self.access_model._is_active())
                self.assertEqual(
                    self.mixin._resolve_model('res.country')._name,
                    'res.country',
                )

    def test_unknown_tool_and_non_object_arguments_reach_the_base_checks(self):
        self._allow('res.partner')
        for name, arguments in (
            ('mcp_access_no_such_tool', {}),
            ('search_read', ['res.partner']),
        ):
            with self.subTest(tool=name), self.assertRaises(UserError):
                self.tool_model._call(name, arguments, self.env)
