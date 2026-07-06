from __future__ import annotations

from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestAutomationCaps(TransactionCase):
    """Test cap resolution for automation-spawned sessions without schedules."""

    @classmethod
    def setUpClass(cls) -> None:
        """Set up an agent, a capped server action, and a bare session."""
        super().setUpClass()
        cls.agent = cls.env['muk_ai.agent'].create({'name': 'Automation Cap Agent'})
        cls.action = cls.env['ir.actions.server'].create(
            {
                'name': 'Capped Agent Action',
                'state': 'ai_agent',
                'model_id': cls.env['ir.model']._get_id('res.partner'),
                'agent_id': cls.agent.id,
                'agent_max_resumes': 2,
                'agent_max_cost_eur': 1.0,
            }
        )
        cls.session = cls.env['muk_ai.session'].create(
            {
                'name': 'Automation Session',
                'agent_id': cls.agent.id,
                'action_server_id': cls.action.id,
            }
        )

    def test_action_caps_resolved_without_schedule(self):
        self.assertFalse(self.session.schedule_id)
        caps = self.env['muk_mcp.mixin']._schedule_effective_caps(self.session)
        self.assertEqual(caps['max_resumes'], 2)
        self.assertEqual(caps['max_cost_eur'], 1.0)
