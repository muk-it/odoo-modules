from __future__ import annotations

from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install', 'muk_ai_automation')
class TestActionAgentFields(TransactionCase):
    """Test the agent fields and defaults on ``ir.actions.server``."""

    @classmethod
    def setUpClass(cls) -> None:
        """Cache the server-action model."""
        super().setUpClass()
        cls.ServerAction = cls.env['ir.actions.server']

    def test_state_agent_selection_present(self):
        selection = dict(self.ServerAction._fields['state'].selection)
        self.assertIn('ai_agent', selection)

    def test_agent_fields_present(self):
        expected = {
            'agent_id',
            'agent_prompt',
            'agent_dispatch_mode',
            'agent_record_source',
            'agent_record_domain',
            'agent_record_code',
            'agent_max_records_per_fire',
            'agent_max_resumes',
            'agent_max_lifetime_hours',
            'agent_max_total_tokens',
            'agent_max_cost_eur',
            'agent_chain_strategy',
        }
        present = set(self.ServerAction._fields) & expected
        self.assertEqual(present, expected)

    def test_default_dispatch_mode_single(self):
        field = self.ServerAction._fields['agent_dispatch_mode']
        default = (
            field.default(self.ServerAction)
            if callable(field.default)
            else field.default
        )
        self.assertEqual(default, 'single')

    def test_default_record_source_domain(self):
        field = self.ServerAction._fields['agent_record_source']
        default = (
            field.default(self.ServerAction)
            if callable(field.default)
            else field.default
        )
        self.assertEqual(default, 'domain')
