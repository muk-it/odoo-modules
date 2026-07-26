from __future__ import annotations

from odoo.tests.common import tagged

from .common import AutomationTestCommon
from odoo.addons.muk_ai_automation.tools.constants import (
    AGENT_DEFAULT_MAX_COST_EUR,
    AGENT_DEFAULT_MAX_LIFETIME_HOURS,
    AGENT_DEFAULT_MAX_RESUMES,
    AGENT_DEFAULT_MAX_TOTAL_TOKENS,
)


@tagged('post_install', '-at_install', 'muk_ai_automation')
class TestCaps(AutomationTestCommon):
    """Test effective cap propagation from action to session."""

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _caps_of_spawned(self, **vals) -> dict:
        """Fire an action built from ``vals`` and return its session caps."""
        action = self._make_action(**vals)
        with self._mock_provider():
            action.run()
        sessions = self._sessions_of(action)
        self.assertEqual(len(sessions), 1)
        return sessions.action_server_id._agent_effective_caps()

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_agent_max_resumes_propagates(self):
        caps = self._caps_of_spawned(agent_max_resumes=7)
        self.assertEqual(caps['max_resumes'], 7)

    def test_agent_max_total_tokens_propagates(self):
        caps = self._caps_of_spawned(agent_max_total_tokens=12345)
        self.assertEqual(caps['max_total_tokens'], 12345)

    def test_caps_default_to_module_defaults_when_zero(self):
        caps = self._caps_of_spawned(
            agent_max_resumes=0,
            agent_max_lifetime_hours=0,
            agent_max_total_tokens=0,
            agent_max_cost_eur=0.0,
        )
        self.assertEqual(caps['max_resumes'], AGENT_DEFAULT_MAX_RESUMES)
        self.assertEqual(caps['max_lifetime_hours'], AGENT_DEFAULT_MAX_LIFETIME_HOURS)
        self.assertEqual(caps['max_total_tokens'], AGENT_DEFAULT_MAX_TOTAL_TOKENS)
        self.assertEqual(caps['max_cost_eur'], AGENT_DEFAULT_MAX_COST_EUR)
