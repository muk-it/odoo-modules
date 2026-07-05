from __future__ import annotations

from contextlib import AbstractContextManager
from datetime import datetime, timedelta
from unittest.mock import patch

from freezegun import freeze_time

from odoo import fields, models
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'muk_ai_schedule')
class TestCronSweep(TransactionCase):
    """Covers owned-cron firing and the scheduled-session pickup sweep."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.provider = cls.env.ref('muk_ai.provider_openai')
        cls.provider.sudo().api_key = 'test-key'
        cls.env.company.default_ai_provider_id = cls.provider
        cls.agent = cls.env['muk_ai.agent'].create(
            {
                'name': 'Cron Sweep Agent',
            }
        )
        cls.partner_model = cls.env['ir.model']._get('res.partner')
        cls.Session = cls.env['muk_ai.session']
        cls.Schedule = cls.env['muk_ai.schedule']

    def _make_schedule(self, **vals) -> models.BaseModel:
        """Create a schedule from the default values overridden by ``vals``."""
        defaults = {
            'name': 'Cron Test Schedule',
            'agent_id': self.agent.id,
            'prompt': 'Hello.',
            'interval_type': 'days',
            'interval_number': 1,
            'dispatch_mode': 'single',
        }
        defaults.update(vals)
        return self.Schedule.create(defaults)

    def _mock_provider(self) -> AbstractContextManager:
        """Return a patch that stubs the provider response request."""
        payload = {
            'text': 'ok',
            'tool_calls': [],
            'carry_inputs': [],
            'usage': {'input_tokens': 1, 'output_tokens': 1, 'cached_tokens': 0},
        }

        def fake(self_arg, *args, **kwargs):
            return payload

        return patch.object(
            type(self.provider),
            '_request_responses',
            autospec=True,
            side_effect=fake,
        )

    # ----------------------------------------------------------
    # Tests Owned Cron Trigger
    # ----------------------------------------------------------

    def test_due_schedule_is_fired(self):
        schedule = self._make_schedule()
        self.assertTrue(schedule.cron_id)
        before = self.Session.search_count([('schedule_id', '=', schedule.id)])
        with self._mock_provider():
            schedule.action_fire_now()
        after = self.Session.search_count([('schedule_id', '=', schedule.id)])
        self.assertGreater(after, before)

    def test_inactive_schedule_not_fired(self):
        schedule = self._make_schedule(active=False)
        self.assertTrue(schedule.cron_id)
        self.assertFalse(schedule.cron_id.active)

    def test_due_schedule_advances_nextcall(self):
        schedule = self._make_schedule()
        schedule.cron_id.sudo().nextcall = fields.Datetime.now() - timedelta(minutes=1)
        before = schedule.cron_id.nextcall
        with self._mock_provider():
            schedule.action_fire_now()
        self.assertGreater(schedule.cron_id.nextcall, before)

    def test_owned_cron_is_unique_per_schedule(self):
        sched_a = self._make_schedule(name='Sched A')
        sched_b = self._make_schedule(name='Sched B')
        self.assertNotEqual(sched_a.cron_id, sched_b.cron_id)
        self.assertNotEqual(sched_a.action_server_id, sched_b.action_server_id)

    # ----------------------------------------------------------
    # Tests Owned Cron Reschedule
    # ----------------------------------------------------------

    def _make_job_snapshot(self, cron: models.BaseModel, nextcall: datetime) -> dict:
        """Build the job dict that ir.cron._reschedule_later expects."""
        return {
            'id': cron.id,
            'nextcall': nextcall,
            'interval_type': cron.interval_type,
            'interval_number': cron.interval_number,
        }

    def test_cron_expression_reschedule_follows_expression(self):
        schedule = self._make_schedule(
            interval_type='cron',
            cron_expression='0 9 * * 1',
        )
        cron = schedule.cron_id.sudo()
        now = fields.Datetime.now()
        job = self._make_job_snapshot(cron, now - timedelta(minutes=1))
        self.env['ir.cron']._reschedule_later(job)
        cron.invalidate_recordset(['nextcall'])
        nextcall = cron.nextcall
        self.assertEqual(
            (nextcall.hour, nextcall.minute, nextcall.weekday()), (9, 0, 0)
        )
        self.assertGreater(nextcall, now)

    def test_monthly_monthday_31_does_not_drift_after_auto_fire(self):
        schedule = self._make_schedule(
            interval_type='months',
            interval_number=1,
            monthday=31,
        )
        cron = schedule.cron_id.sudo()
        cron.nextcall = datetime(2026, 2, 28, 9, 0)
        job = self._make_job_snapshot(cron, cron.nextcall)
        with freeze_time('2026-02-28 09:00:05'):
            self.env['ir.cron']._reschedule_later(job)
        cron.invalidate_recordset(['nextcall'])
        self.assertEqual(
            (cron.nextcall.year, cron.nextcall.month, cron.nextcall.day),
            (2026, 3, 31),
        )

    # ----------------------------------------------------------
    # Tests _find_pending_session_ids extension
    # ----------------------------------------------------------

    def test_schedule_state_with_past_resume_at_picked_up(self):
        session = self.Session.create(
            {
                'name': 'Waiting Test',
                'agent_id': self.agent.id,
            }
        )
        session.write(
            {
                'state': 'schedule',
                'resume_at': fields.Datetime.now() - timedelta(minutes=1),
            }
        )
        self.env.flush_all()
        ids = self.Session._find_pending_session_ids()
        self.assertIn(session.id, ids)

    def test_schedule_state_with_future_resume_at_not_picked(self):
        session = self.Session.create(
            {
                'name': 'Waiting Future',
                'agent_id': self.agent.id,
            }
        )
        session.write(
            {
                'state': 'schedule',
                'resume_at': fields.Datetime.now() + timedelta(hours=1),
            }
        )
        self.env.flush_all()
        ids = self.Session._find_pending_session_ids()
        self.assertNotIn(session.id, ids)

    def test_schedule_state_with_no_resume_at_not_picked(self):
        session = self.Session.create(
            {
                'name': 'Waiting No Time',
                'agent_id': self.agent.id,
            }
        )
        session.write({'state': 'schedule'})
        self.env.flush_all()
        ids = self.Session._find_pending_session_ids()
        self.assertNotIn(session.id, ids)
