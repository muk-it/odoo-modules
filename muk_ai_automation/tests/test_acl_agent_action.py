from __future__ import annotations

from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install', 'muk_ai_automation')
class TestAclAgentAction(TransactionCase):
    """Test access control for creating ``ai_agent`` server actions."""

    @classmethod
    def setUpClass(cls) -> None:
        """Create the shared agent and partner model record."""
        super().setUpClass()
        cls.agent = cls.env['muk_ai.agent'].create(
            {
                'name': 'ACL Agent',
            }
        )
        cls.partner_model = cls.env['ir.model']._get('res.partner')

    def _vals(self) -> dict:
        """Return valid values for an ``ai_agent`` server action."""
        return {
            'name': 'ACL Action',
            'state': 'ai_agent',
            'model_id': self.partner_model.id,
            'agent_id': self.agent.id,
            'agent_prompt': 'Hello.',
            'agent_dispatch_mode': 'single',
            'agent_record_source': 'domain',
            'agent_record_domain': '[]',
        }

    def test_internal_user_cannot_create_state_agent_action(self):
        user = new_test_user(self.env, login='user_a', groups='base.group_user')
        with self.assertRaises(AccessError):
            self.env['ir.actions.server'].with_user(user).create(self._vals())

    def test_admin_can_create_state_agent_action(self):
        action = self.env['ir.actions.server'].create(self._vals())
        self.assertTrue(action.exists())
        self.assertEqual(action.state, 'ai_agent')
