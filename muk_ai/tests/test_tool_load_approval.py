from __future__ import annotations

from odoo.addons.muk_ai.tests.common import AITestCommon, ToolCatalogMixin


class TestToolLoadInlineApproval(ToolCatalogMixin, AITestCommon):
    """Verify a tool_load inline call honours the risky-write approval gate."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls._mark_sensitive('res.partner')
        cls.session = cls.env['muk_ai.session'].create({'name': 'Inline gate'})
        cls.catalog = [
            {
                'name': 'update_records',
                'description': 'Update records',
                'inputSchema': {'type': 'object'},
            },
        ]

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _inline_load(self, model: str) -> dict:
        """Build tool_load arguments whose inline call updates ``model``."""
        return {
            'names': ['update_records'],
            'call': {
                'name': 'update_records',
                'arguments': {
                    'model': model,
                    'ids': [1],
                    'values': {'name': 'Owned'},
                },
            },
        }

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_inline_call_defers_risky_write_without_executing(self):
        tool_patch, calls = self._patch_tool({'update_records': '{"success": true}'})
        with self._patch_catalog(), tool_patch:
            response = self.session._dispatch_tool_load(
                self._inline_load('res.partner'),
                parent_call_id='c1',
            )
        inline = response['call']
        self.assertFalse(inline['ok'])
        self.assertEqual(inline['output']['error'], 'requires_approval')
        self.assertNotIn('update_records', calls)

    def test_inline_call_dispatches_when_model_not_sensitive(self):
        tool_patch, calls = self._patch_tool({'update_records': '{"success": true}'})
        with self._patch_catalog(), tool_patch:
            response = self.session._dispatch_tool_load(
                self._inline_load('res.partner.category'),
                parent_call_id='c2',
            )
        inline = response['call']
        self.assertTrue(inline['ok'])
        self.assertIn('update_records', calls)

    def test_inline_call_dispatches_when_approval_off(self):
        self.session.override_approval_mode = 'off'
        tool_patch, calls = self._patch_tool({'update_records': '{"success": true}'})
        with self._patch_catalog(), tool_patch:
            response = self.session._dispatch_tool_load(
                self._inline_load('res.partner'),
                parent_call_id='c3',
            )
        inline = response['call']
        self.assertTrue(inline['ok'])
        self.assertIn('update_records', calls)
