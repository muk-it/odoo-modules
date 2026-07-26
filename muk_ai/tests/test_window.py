from __future__ import annotations

import json

from odoo.exceptions import UserError

from odoo.addons.muk_ai.tests.common import AITestCommon


class TestAiWindow(AITestCommon):
    """Verify the open_record/open_view/open_action navigation tools."""

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _call(self, name: str, arguments: dict) -> dict:
        """Run the named tool and return its JSON-decoded result."""
        text, _info = self.env['muk_mcp.tool']._call(name, arguments, self.env)
        return json.loads(text)

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_open_view_basic(self):
        result = self._call('open_view', {'model': 'res.partner'})
        self.assertEqual(result['type'], 'ir.actions.act_window')
        self.assertEqual(result['res_model'], 'res.partner')
        self.assertEqual(result['view_mode'], 'list')
        self.assertNotIn('context', result)

    def test_open_view_passes_additional_context(self):
        result = self._call(
            'open_view',
            {
                'model': 'res.partner',
                'view_type': 'pivot',
                'additional_context': {
                    'pivot_row_groupby': ['country_id'],
                    'pivot_measures': ['__count'],
                },
            },
        )
        self.assertEqual(result['view_mode'], 'pivot')
        self.assertEqual(
            result['context']['pivot_row_groupby'],
            ['country_id'],
        )
        self.assertEqual(result['context']['pivot_measures'], ['__count'])

    def test_open_view_empty_additional_context_omits_key(self):
        result = self._call(
            'open_view',
            {
                'model': 'res.partner',
                'additional_context': {},
            },
        )
        self.assertNotIn('context', result)

    def test_open_view_graph_context(self):
        result = self._call(
            'open_view',
            {
                'model': 'res.partner',
                'view_type': 'graph',
                'additional_context': {
                    'graph_mode': 'bar',
                    'graph_groupbys': ['country_id'],
                    'graph_measure': '__count',
                },
            },
        )
        self.assertEqual(result['context']['graph_mode'], 'bar')
        self.assertEqual(result['context']['graph_groupbys'], ['country_id'])

    def test_open_view_normalizes_tree_to_list(self):
        result = self._call(
            'open_view',
            {
                'model': 'res.partner',
                'view_type': 'tree',
            },
        )
        self.assertEqual(result['view_mode'], 'list')

    def test_open_view_rejects_unknown_view_type(self):
        with self.assertRaises(UserError):
            self._call(
                'open_view',
                {
                    'model': 'res.partner',
                    'view_type': 'bogus',
                },
            )

    def test_open_view_rejects_unknown_target(self):
        with self.assertRaises(UserError):
            self._call(
                'open_view',
                {
                    'model': 'res.partner',
                    'target': 'bogus',
                },
            )

    def test_open_view_attaches_breadcrumb_name(self):
        result = self._call(
            'open_view',
            {
                'model': 'res.partner',
                'name': 'My Partners',
            },
        )
        self.assertEqual(result['name'], 'My Partners')

    # ----------------------------------------------------------
    # open_record
    # ----------------------------------------------------------

    def test_open_record_returns_form_act_window(self):
        partner = self.env['res.partner'].create({'name': 'OpenMe'})
        result = self._call(
            'open_record',
            {
                'model': 'res.partner',
                'res_id': partner.id,
            },
        )
        self.assertEqual(result['type'], 'ir.actions.act_window')
        self.assertEqual(result['res_model'], 'res.partner')
        self.assertEqual(result['res_id'], partner.id)
        self.assertEqual(result['view_mode'], 'form')
        self.assertEqual(result['target'], 'current')

    def test_open_record_honours_view_type(self):
        partner = self.env['res.partner'].create({'name': 'OpenMe2'})
        result = self._call(
            'open_record',
            {
                'model': 'res.partner',
                'res_id': partner.id,
                'view_type': 'kanban',
            },
        )
        self.assertEqual(result['view_mode'], 'kanban')

    # ----------------------------------------------------------
    # open_action
    # ----------------------------------------------------------

    def test_open_action_by_xmlid_returns_descriptor(self):
        result = self._call('open_action', {'action_ref': 'base.action_partner_form'})
        self.assertIn('res_model', result)
        self.assertEqual(result['res_model'], 'res.partner')

    def test_open_action_by_numeric_id(self):
        action = self.env.ref('base.action_partner_form')
        result = self._call('open_action', {'action_ref': action.id})
        self.assertEqual(result['res_model'], 'res.partner')

    def test_open_action_merges_additional_context(self):
        result = self._call(
            'open_action',
            {
                'action_ref': 'base.action_partner_form',
                'additional_context': {'default_name': 'Preset'},
            },
        )
        self.assertEqual(result['context']['default_name'], 'Preset')

    # ----------------------------------------------------------
    # show_notification
    # ----------------------------------------------------------

    def test_show_notification_basic(self):
        result = self._call('show_notification', {'message': 'Hello'})
        self.assertEqual(result['type'], 'ir.actions.client')
        self.assertEqual(result['tag'], 'display_notification')
        self.assertEqual(result['params']['message'], 'Hello')
        self.assertEqual(result['params']['type'], 'info')
        self.assertFalse(result['params']['sticky'])
        self.assertNotIn('title', result['params'])

    def test_show_notification_with_title_and_sticky(self):
        result = self._call(
            'show_notification',
            {
                'message': 'Saved',
                'title': 'All good',
                'type': 'success',
                'sticky': True,
            },
        )
        self.assertEqual(result['params']['title'], 'All good')
        self.assertEqual(result['params']['type'], 'success')
        self.assertTrue(result['params']['sticky'])
