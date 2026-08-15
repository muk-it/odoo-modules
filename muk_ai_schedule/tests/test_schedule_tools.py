from __future__ import annotations

from datetime import timedelta

from odoo import fields, models
from odoo.exceptions import UserError
from odoo.tests.common import tagged

from .common import ScheduleTestCommon
from odoo.addons.muk_ai_schedule.tools.constants import (
    DEFAULT_MAX_COST_EUR,
    DEFAULT_MAX_RESUMES,
)


@tagged('post_install', '-at_install', 'muk_ai_schedule')
class TestScheduleTools(ScheduleTestCommon):
    """Covers the schedule_resume and schedule_recurring MCP tool behaviours."""

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _arm_recurring(self, session: models.BaseModel, **vals) -> None:
        """Put ``session`` in the state a finished recurring fire leaves behind."""
        until = fields.Datetime.to_string(fields.Datetime.now() + timedelta(days=20))
        values = {
            'state': 'done',
            'recur_config': {
                'every': 3600,
                'until': until,
                'max_runs': None,
                'started_at': fields.Datetime.to_string(fields.Datetime.now()),
                'prompt': 'ping',
            },
            'recur_runs_done': 3,
        }
        values.update(vals)
        session.write(values)

    # ----------------------------------------------------------
    # Tests schedule_resume
    # ----------------------------------------------------------

    def test_schedule_resume_seconds_from_now_sets_resume_at(self):
        session = self._make_session()
        before = fields.Datetime.now()
        result = self._mixin_for(session)._mcp_schedule_resume(
            seconds_from_now=120,
            prompt='ping',
        )
        self.assertTrue(result['ok'])
        self.assertEqual(session.state, 'schedule')
        self.assertTrue(session.resume_at)
        delta = (session.resume_at - before).total_seconds()
        self.assertGreaterEqual(delta, 119)
        self.assertLessEqual(delta, 122)

    def test_schedule_resume_at_string_sets_resume_at(self):
        session = self._make_session()
        target = fields.Datetime.now() + timedelta(hours=1)
        target_str = fields.Datetime.to_string(target)
        result = self._mixin_for(session)._mcp_schedule_resume(
            at=target_str,
            prompt='ping',
        )
        self.assertTrue(result['ok'])
        self.assertEqual(session.state, 'schedule')
        delta = abs((session.resume_at - target).total_seconds())
        self.assertLess(delta, 2)

    def test_schedule_resume_rejects_both_args(self):
        session = self._make_session()
        with self.assertRaises(UserError):
            self._mixin_for(session)._mcp_schedule_resume(
                at='2099-01-01 00:00:00',
                seconds_from_now=120,
                prompt='ping',
            )

    def test_schedule_resume_rejects_neither_arg(self):
        session = self._make_session()
        with self.assertRaises(UserError):
            self._mixin_for(session)._mcp_schedule_resume(prompt='ping')

    def test_schedule_resume_min_delay_violation(self):
        session = self._make_session()
        with self.assertRaises(UserError):
            self._mixin_for(session)._mcp_schedule_resume(
                seconds_from_now=10,
                prompt='ping',
            )

    def test_schedule_resume_max_delay_violation(self):
        session = self._make_session()
        with self.assertRaises(UserError):
            self._mixin_for(session)._mcp_schedule_resume(
                seconds_from_now=99_999_999,
                prompt='ping',
            )

    def test_schedule_resume_requires_session_context(self):
        with self.assertRaises(UserError):
            self.Mixin._mcp_schedule_resume(
                seconds_from_now=120,
                prompt='ping',
            )

    # ----------------------------------------------------------
    # Tests schedule_recurring
    # ----------------------------------------------------------

    def test_schedule_recurring_persists_config(self):
        session = self._make_session()
        result = self._mixin_for(session)._mcp_schedule_recurring(
            every=120,
            max_runs=3,
            prompt='ping',
        )
        self.assertTrue(result['ok'])
        self.assertEqual(session.state, 'schedule')
        config = session.recur_config or {}
        self.assertEqual(config.get('every'), 120)
        self.assertEqual(config.get('max_runs'), 3)
        self.assertTrue(config.get('started_at'))
        self.assertEqual(session.recur_runs_done, 1)

    def test_schedule_recurring_refuses_after_max_runs(self):
        session = self._make_session()
        session.write(
            {
                'recur_config': {
                    'every': 120,
                    'max_runs': 3,
                    'started_at': fields.Datetime.to_string(fields.Datetime.now()),
                    'prompt': 'ping',
                },
                'recur_runs_done': 3,
            }
        )
        result = self._mixin_for(session)._mcp_schedule_recurring(
            every=120,
            max_runs=3,
            prompt='ping',
        )
        self.assertFalse(result['ok'])
        self.assertEqual(result['cap'], 'recur_max_runs')
        self.assertEqual(session.state, 'error')
        events = self.env['muk_ai.session.event'].search(
            [
                ('session_id', '=', session.id),
                ('kind', '=', 'cap_exceeded'),
            ]
        )
        self.assertEqual(len(events), 1)

    def test_schedule_recurring_rejects_both_until_and_max_runs(self):
        session = self._make_session()
        future = fields.Datetime.to_string(fields.Datetime.now() + timedelta(days=1))
        with self.assertRaises(UserError):
            self._mixin_for(session)._mcp_schedule_recurring(
                every=120,
                until=future,
                max_runs=3,
                prompt='ping',
            )

    def test_schedule_recurring_rejects_neither_until_nor_max_runs(self):
        session = self._make_session()
        with self.assertRaises(UserError):
            self._mixin_for(session)._mcp_schedule_recurring(
                every=120,
                prompt='ping',
            )

    # ----------------------------------------------------------
    # Tests Recurring Redefer
    # ----------------------------------------------------------

    def test_auto_redefer_stops_on_the_cost_cap(self):
        session = self._make_session()
        self._arm_recurring(session, total_cost=DEFAULT_MAX_COST_EUR * 20)
        session._auto_redefer_recurring()
        self.assertEqual(session.state, 'error')
        self.assertFalse(session.resume_at)
        events = self.Event.search(
            [
                ('session_id', '=', session.id),
                ('kind', '=', 'cap_exceeded'),
            ]
        )
        self.assertEqual(len(events), 1)
        self.assertEqual(events.payload.get('cap'), 'max_cost_eur')

    def test_auto_redefer_stops_on_the_resume_cap(self):
        session = self._make_session()
        self._arm_recurring(session, recur_runs_done=DEFAULT_MAX_RESUMES + 10)
        session._auto_redefer_recurring()
        self.assertNotEqual(session.state, 'schedule')
        self.assertFalse(session.resume_at)

    def test_auto_redefer_rearms_while_within_the_caps(self):
        session = self._make_session()
        self._arm_recurring(session)
        session._auto_redefer_recurring()
        self.assertEqual(session.state, 'schedule')
        self.assertTrue(session.resume_at)
        self.assertEqual(session.recur_runs_done, 4)

    # ----------------------------------------------------------
    # Tests Cap Exceeded
    # ----------------------------------------------------------

    def test_cap_exceeded_posts_event(self):
        schedule = self._make_schedule(max_resumes=2)
        session = self._make_session(schedule_id=schedule.id)
        session.write({'recur_runs_done': 5})
        result = self._mixin_for(session)._mcp_schedule_resume(
            seconds_from_now=120,
            prompt='ping',
        )
        self.assertFalse(result['ok'])
        self.assertEqual(result['cap'], 'max_resumes')
        self.assertEqual(session.state, 'error')
        events = self.env['muk_ai.session.event'].search(
            [
                ('session_id', '=', session.id),
                ('kind', '=', 'cap_exceeded'),
            ]
        )
        self.assertEqual(len(events), 1)
        self.assertEqual(events.payload.get('cap'), 'max_resumes')
