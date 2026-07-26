from __future__ import annotations

from odoo.addons.muk_ai.tests.common import AITestCommon


class TestApprovalRiskPredicate(AITestCommon):
    """Verify which tool calls are classified as risky and require approval."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls._mark_sensitive('res.partner', 'muk_ai.session')

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_delete_on_sensitive_model_is_risky(self):
        risk = self.env['muk_ai.approval']._assess_risk(
            'delete_records',
            {
                'model': 'res.partner',
                'ids': [1, 2],
            },
        )
        self.assertIsNotNone(risk)
        self.assertEqual(risk['tool'], 'delete_records')
        self.assertTrue(risk['signature'])
        self.assertIn('flagged sensitive', risk['reason'])

    def test_call_method_on_sensitive_model_is_risky(self):
        risk = self.env['muk_ai.approval']._assess_risk(
            'call_method',
            {
                'model': 'res.partner',
                'method': 'action_archive',
                'ids': [1],
            },
        )
        self.assertIsNotNone(risk)
        self.assertEqual(risk['method'], 'action_archive')
        self.assertIn('action_archive', risk['reason'])

    def test_update_on_sensitive_model_is_risky(self):
        risk = self.env['muk_ai.approval']._assess_risk(
            'update_records',
            {
                'model': 'res.partner',
                'ids': [1],
                'values': {'user_id': 1},
            },
        )
        self.assertIsNotNone(risk)
        self.assertEqual(risk['tool'], 'update_records')

    def test_update_on_non_sensitive_model_is_safe(self):
        risk = self.env['muk_ai.approval']._assess_risk(
            'update_records',
            {
                'model': 'res.partner.category',
                'ids': [1],
                'values': {'name': 'tag'},
            },
        )
        self.assertIsNone(risk)

    def test_create_on_sensitive_model_is_risky(self):
        risk = self.env['muk_ai.approval']._assess_risk(
            'create_records',
            {
                'model': 'res.users',
                'values': {'name': 'X'},
            },
        )
        self.assertIsNotNone(risk)

    def test_create_on_non_sensitive_model_is_safe(self):
        risk = self.env['muk_ai.approval']._assess_risk(
            'create_records',
            {
                'model': 'res.partner.category',
                'values': {'name': 'Tag'},
            },
        )
        self.assertIsNone(risk)

    def test_signature_stable_for_same_tool_and_model(self):
        a = self.env['muk_ai.approval']._assess_risk(
            'update_records',
            {
                'model': 'res.partner',
                'ids': [1],
                'values': {'user_id': 2},
            },
        )
        b = self.env['muk_ai.approval']._assess_risk(
            'update_records',
            {
                'model': 'res.partner',
                'ids': [9],
                'values': {'user_id': 3},
            },
        )
        self.assertEqual(a['signature'], b['signature'])

    def test_signature_differs_when_tool_differs(self):
        a = self.env['muk_ai.approval']._assess_risk(
            'delete_records',
            {
                'model': 'res.partner',
                'ids': [1],
            },
        )
        b = self.env['muk_ai.approval']._assess_risk(
            'update_records',
            {
                'model': 'res.partner',
                'ids': [1],
                'values': {'name': 'X'},
            },
        )
        self.assertNotEqual(a['signature'], b['signature'])

    def test_signature_differs_when_method_differs(self):
        a = self.env['muk_ai.approval']._assess_risk(
            'call_method',
            {
                'model': 'res.partner',
                'ids': [1],
                'method': 'action_archive',
            },
        )
        b = self.env['muk_ai.approval']._assess_risk(
            'call_method',
            {
                'model': 'res.partner',
                'ids': [1],
                'method': 'action_unarchive',
            },
        )
        self.assertNotEqual(a['signature'], b['signature'])
