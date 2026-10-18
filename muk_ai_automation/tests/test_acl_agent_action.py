from __future__ import annotations

from odoo.exceptions import AccessError
from odoo.tests.common import new_test_user, tagged

from .common import AutomationTestCommon


@tagged('post_install', '-at_install', 'muk_ai_automation')
class TestAclAgentAction(AutomationTestCommon):
    """Test access control for creating ``ai_agent`` server actions."""

    def test_internal_user_cannot_create_state_agent_action(self):
        user = new_test_user(self.env, login='user_a', groups='base.group_user')
        with self.assertRaises(AccessError):
            self.env['ir.actions.server'].with_user(user).create(self._action_vals())

    def test_owner_renders_the_prompt_of_a_chat_from_a_hidden_action(self):
        user = new_test_user(self.env, login='user_b', groups='base.group_user')
        session = self.env['muk_ai.session'].create(
            {
                'name': 'Action Chat',
                'user_id': user.id,
                'action_server_id': self._make_action().id,
            }
        )
        self.assertFalse(session.with_user(user)._session_prompt_extras()['records'])
