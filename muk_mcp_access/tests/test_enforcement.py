from __future__ import annotations

import json
from typing import Any

from odoo import models
from odoo.exceptions import AccessError
from odoo.tests import common, tagged

from odoo.addons.muk_mcp.core.tool import invalidate_registry_cache, mcp_tool


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


@tagged('post_install', '-at_install')
class TestMCPAccessEnforcement(common.TransactionCase):
    """Cover the tool-category enforcement path from ``_call`` to ``_resolve_model``."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
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
        """Invoke an MCP tool the way a cron or direct ORM caller does.

        No HTTP request is bound, which is exactly the situation in which the
        write restriction used to be skipped.
        """
        text, _info = self.tool_model._call(name, arguments, self.env)
        return json.loads(text) if isinstance(text, str) else text

    def _new_partner(self, name: str) -> models.BaseModel:
        """Create a plain partner to act on through the write tools."""
        return self.env['res.partner'].create({'name': name})

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_create_records_denied_on_read_only_model_without_request(self):
        self._allow('res.partner', read=True, write=False)
        with self.assertRaises(AccessError):
            self._call_tool(
                'create_records',
                {'model': 'res.partner', 'values': {'name': 'MCP_NO_REQUEST'}},
            )
        self.assertFalse(
            self.env['res.partner'].search([('name', '=', 'MCP_NO_REQUEST')]),
        )

    def test_create_records_allowed_on_write_model_without_request(self):
        self._allow('res.partner', read=True, write=True)
        result = self._call_tool(
            'create_records',
            {'model': 'res.partner', 'values': {'name': 'MCP_WRITE_OK'}},
        )
        self.assertTrue(result['id'])

    def test_update_records_denied_on_read_only_model_without_request(self):
        self._allow('res.partner', read=True, write=False)
        partner = self._new_partner('MCP_UPDATE_DENIED')
        with self.assertRaises(AccessError):
            self._call_tool(
                'update_records',
                {
                    'model': 'res.partner',
                    'ids': [partner.id],
                    'values': {'function': 'changed'},
                },
            )
        self.assertFalse(partner.function)

    def test_update_records_allowed_on_write_model_without_request(self):
        self._allow('res.partner', read=True, write=True)
        partner = self._new_partner('MCP_UPDATE_OK')
        self._call_tool(
            'update_records',
            {
                'model': 'res.partner',
                'ids': [partner.id],
                'values': {'function': 'changed'},
            },
        )
        self.assertEqual(partner.function, 'changed')

    def test_delete_records_denied_on_read_only_model_without_request(self):
        self._allow('res.partner', read=True, write=False)
        partner = self._new_partner('MCP_DELETE_DENIED')
        with self.assertRaises(AccessError):
            self._call_tool(
                'delete_records',
                {'model': 'res.partner', 'ids': [partner.id]},
            )
        self.assertTrue(partner.exists())

    def test_delete_records_allowed_on_write_model_without_request(self):
        self._allow('res.partner', read=True, write=True)
        partner = self._new_partner('MCP_DELETE_OK')
        self._call_tool(
            'delete_records',
            {'model': 'res.partner', 'ids': [partner.id]},
        )
        self.assertFalse(partner.exists())

    def test_call_method_denied_on_read_only_model_without_request(self):
        self._allow('res.partner', read=True, write=False)
        partner = self._new_partner('MCP_CALL_DENIED')
        with self.assertRaises(AccessError):
            self._call_tool(
                'call_method',
                {
                    'model': 'res.partner',
                    'method': 'write',
                    'ids': [partner.id],
                    'args': '[{"function": "changed"}]',
                },
            )
        self.assertFalse(partner.function)

    def test_call_method_allowed_on_write_model_without_request(self):
        self._allow('res.partner', read=True, write=True)
        partner = self._new_partner('MCP_CALL_OK')
        self._call_tool(
            'call_method',
            {
                'model': 'res.partner',
                'method': 'write',
                'ids': [partner.id],
                'args': '[{"function": "changed"}]',
            },
        )
        self.assertEqual(partner.function, 'changed')

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

    def test_write_only_entry_denies_read_tool_and_allows_write_tool(self):
        self._allow('res.partner', read=False, write=True)
        with self.assertRaises(AccessError):
            self._call_tool(
                'search_read',
                {'model': 'res.partner', 'fields': ['name']},
            )
        result = self._call_tool(
            'create_records',
            {'model': 'res.partner', 'values': {'name': 'MCP_WRITE_ONLY'}},
        )
        self.assertTrue(result['id'])

    def test_read_only_entry_allows_read_tool_and_denies_write_tool(self):
        self._allow('res.partner', read=True, write=False)
        rows = self._call_tool(
            'search_read',
            {'model': 'res.partner', 'fields': ['name'], 'limit': 1},
        )
        self.assertIsInstance(rows, list)
        with self.assertRaises(AccessError):
            self._call_tool(
                'create_records',
                {'model': 'res.partner', 'values': {'name': 'MCP_READ_ONLY'}},
            )

    def test_unlisted_model_denied_for_sudo_and_admin(self):
        self._allow('res.partner')
        admin = self.env.ref('base.user_admin')
        with self.assertRaises(AccessError):
            self.mixin.sudo()._resolve_model('res.country')
        with self.assertRaises(AccessError):
            self.mixin.with_user(admin)._resolve_model('res.country')

    def test_archiving_every_entry_reopens_the_whole_registry(self):
        entry = self.access_model.create(
            {
                'model_id': self.env['ir.model']._get_id('res.partner'),
                'allow_read': True,
            }
        )
        self.assertTrue(self.access_model._is_active())
        with self.assertRaises(AccessError):
            self.mixin._resolve_model('res.country')
        entry.active = False
        self.assertFalse(self.access_model._is_active())
        self.assertEqual(
            self.mixin._resolve_model('res.country')._name,
            'res.country',
        )

    def test_deleting_every_entry_reopens_the_whole_registry(self):
        entry = self.access_model.create(
            {
                'model_id': self.env['ir.model']._get_id('res.partner'),
                'allow_read': True,
            }
        )
        with self.assertRaises(AccessError):
            self.mixin._resolve_model('res.country')
        entry.unlink()
        self.assertFalse(self.access_model._is_active())
        self.assertEqual(
            self.mixin._resolve_model('res.country')._name,
            'res.country',
        )
