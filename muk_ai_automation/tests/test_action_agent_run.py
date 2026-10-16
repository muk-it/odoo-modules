from __future__ import annotations

from odoo.exceptions import UserError
from odoo.tests.common import tagged

from .common import AutomationTestCommon


@tagged('post_install', '-at_install', 'muk_ai_automation')
class TestActionAgentRun(AutomationTestCommon):
    """Test session spawning when running an ``ai_agent`` server action."""

    @classmethod
    def setUpClass(cls) -> None:
        """Add the partners the per-record dispatch fans out over."""
        super().setUpClass()
        cls.partners = cls._make_partners(3, prefix='Action Partner')

    def test_run_action_agent_single_creates_one_session(self):
        action = self._make_action()
        with self._mock_provider():
            action.run()
        self.assertEqual(len(self._sessions_of(action)), 1)

    def test_run_action_agent_per_record_creates_n_sessions(self):
        action = self._make_action(
            agent_dispatch_mode='per_record',
            agent_record_domain=self._domain_for(self.partners),
            agent_max_records_per_fire=100,
        )
        with self._mock_provider():
            action.run()
        self.assertEqual(len(self._sessions_of(action)), 3)

    def test_run_without_agent_raises(self):
        action = self._make_action()
        action.agent_id = False
        with self._mock_provider(), self.assertRaises(UserError):
            action.run()

    def test_run_with_archived_agent_raises_and_spawns_nothing(self):
        action = self._make_action()
        action.agent_id.active = False
        with self._mock_provider(), self.assertRaises(UserError):
            action.run()
        self.assertFalse(self._sessions_of(action))

    def test_action_chats_land_in_their_space(self):
        custom = (
            self.env['muk_ai.space']
            .sudo()
            .create({'name': 'Partner Review', 'domain': "[('id', '=', 0)]"})
        )
        cron = self.env['ir.cron'].create(
            {
                'name': 'Weekly Review',
                'model_id': self.partner_model.id,
                'state': 'ai_agent',
                'agent_id': self.agent.id,
                'agent_prompt': 'Hello.',
                'interval_type': 'days',
                'interval_number': 1,
            }
        )
        actions = (
            self._make_action(
                agent_dispatch_mode='per_record',
                agent_record_domain=self._domain_for(self._make_partners(2)),
            ),
            cron.ir_actions_server_id,
            self._make_action(agent_space_id=custom.id),
        )
        with self._mock_provider():
            for action in actions:
                action.run()
        spaces = (
            self.env.ref('muk_ai_automation.space_automation'),
            self.env.ref('muk_ai_automation.space_scheduled'),
            custom,
        )
        sessions = self.env['muk_ai.session']
        chats = sessions.concat(*(self._sessions_of(action) for action in actions))
        for action, space in zip(actions, spaces, strict=True):
            with self.subTest(space=space.name):
                self.assertEqual(
                    sessions.search(space._session_domain()) & chats,
                    self._sessions_of(action),
                )
        self.assertFalse(
            sessions.search(sessions.env['muk_ai.space']._unclaimed_session_domain())
            & self._sessions_of(actions[0])
        )
        records = self.env.ref('muk_ai_chatter.space_records')
        self.assertEqual(len(self._sessions_of(actions[0]).filtered('res_id')), 2)
        self.assertFalse(sessions.search(records._session_domain()) & chats)
