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
