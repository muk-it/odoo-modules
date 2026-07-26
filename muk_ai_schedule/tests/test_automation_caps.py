from __future__ import annotations

from odoo.tests.common import tagged

from .common import ScheduleTestCommon
from odoo.addons.muk_ai_schedule.tools.constants import (
    DEFAULT_MAX_COST_EUR,
    DEFAULT_MAX_RESUMES,
)


@tagged('post_install', '-at_install', 'muk_ai_schedule')
class TestAutomationCaps(ScheduleTestCommon):
    """Covers cap resolution when a session has no schedule of its own."""

    def test_action_caps_win_over_the_module_defaults(self):
        action = self.env['ir.actions.server'].create(
            {
                'name': 'Capped Agent Action',
                'state': 'ai_agent',
                'model_id': self.partner_model.id,
                'agent_id': self.agent.id,
                'agent_max_resumes': 2,
                'agent_max_cost_eur': 1.0,
            }
        )
        session = self._make_session(action_server_id=action.id)
        self.assertFalse(session.schedule_id)
        caps = self.Mixin._schedule_effective_caps(session)
        self.assertEqual(caps['max_resumes'], 2)
        self.assertEqual(caps['max_cost_eur'], 1.0)

    def test_a_bare_session_falls_back_to_the_module_defaults(self):
        session = self._make_session()
        self.assertFalse(session.schedule_id)
        self.assertFalse(session.action_server_id)
        caps = self.Mixin._schedule_effective_caps(session)
        self.assertEqual(caps['max_resumes'], DEFAULT_MAX_RESUMES)
        self.assertEqual(caps['max_cost_eur'], DEFAULT_MAX_COST_EUR)

    def test_the_schedule_caps_win_over_the_action_caps(self):
        schedule = self._make_schedule(max_resumes=9, max_cost_eur=3.0)
        session = self._make_session(schedule_id=schedule.id)
        caps = self.Mixin._schedule_effective_caps(session)
        self.assertEqual(caps['max_resumes'], 9)
        self.assertEqual(caps['max_cost_eur'], 3.0)
