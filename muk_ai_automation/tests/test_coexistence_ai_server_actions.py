from __future__ import annotations

from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install', 'muk_ai_automation')
class TestCoexistenceAiServerActions(TransactionCase):
    """Test coexistence with the optional ``ai_server_actions`` module."""

    @classmethod
    def setUpClass(cls) -> None:
        """Create the shared agent and partner model record."""
        super().setUpClass()
        cls.agent = cls.env['muk_ai.agent'].create(
            {
                'name': 'Coexist Agent',
            }
        )
        cls.partner_model = cls.env['ir.model']._get('res.partner')

    def test_evaluation_type_ai_computed_and_state_agent_coexist(self):
        installed = self.env['ir.module.module'].search(
            [
                ('name', '=', 'ai_server_actions'),
                ('state', '=', 'installed'),
            ]
        )
        if not installed:
            self.skipTest('ai_server_actions module is not installed')
        action = self.env['ir.actions.server'].create(
            {
                'name': 'Coexist Action',
                'state': 'ai_agent',
                'model_id': self.partner_model.id,
                'agent_id': self.agent.id,
                'agent_prompt': 'Hello.',
                'agent_dispatch_mode': 'single',
                'agent_record_source': 'domain',
                'agent_record_domain': '[]',
            }
        )
        self.assertTrue(action.exists())
        self.assertEqual(action.state, 'ai_agent')
        fields = self.env['ir.actions.server']._fields
        self.assertIn('evaluation_type', fields)
        self.assertIn('agent_id', fields)
