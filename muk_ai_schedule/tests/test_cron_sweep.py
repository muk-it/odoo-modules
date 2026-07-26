from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import patch

from freezegun import freeze_time

from odoo import fields, models
from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import new_test_user

from .common import ScheduleTestCommon
from odoo.addons.muk_ai_schedule.models import ai_session


@tagged('post_install', '-at_install', 'muk_ai_schedule')
class TestCronSweep(ScheduleTestCommon):
    """Covers owned-cron firing and the scheduled-session pickup sweep."""

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

    def test_due_schedule_advances_nextcall(self):
        schedule = self._make_schedule()
        schedule.cron_id.sudo().nextcall = fields.Datetime.now() - timedelta(minutes=1)
        before = schedule.cron_id.nextcall
        with self._mock_provider():
            schedule.action_fire_now()
        self.assertGreater(schedule.cron_id.nextcall, before)

    def test_long_overdue_schedule_fires_once_and_rebases_on_now(self):
        schedule = self._make_schedule()
        schedule.cron_id.sudo().nextcall = fields.Datetime.now() - timedelta(days=9)
        before = self.Session.search_count([('schedule_id', '=', schedule.id)])
        now = fields.Datetime.now()
        with self._mock_provider():
            schedule.action_fire_now()
        after = self.Session.search_count([('schedule_id', '=', schedule.id)])
        self.assertEqual(after - before, 1)
        self.assertGreater(schedule.cron_id.nextcall, now)
        self.assertLess(
            schedule.cron_id.nextcall - now,
            timedelta(days=1, minutes=1),
        )

    def test_unlink_removes_owned_cron_and_action(self):
        schedule = self._make_schedule()
        cron = schedule.cron_id.sudo()
        action = schedule.action_server_id.sudo()
        schedule.unlink()
        self.assertFalse(cron.exists())
        self.assertFalse(action.exists())

    # ----------------------------------------------------------
    # Tests Owned Cron Sync
    # ----------------------------------------------------------

    def test_renaming_schedule_does_not_move_nextcall(self):
        schedule = self._make_schedule()
        before = schedule.cron_id.nextcall
        schedule.write({'name': 'Renamed Schedule', 'prompt': 'New prompt.'})
        self.assertEqual(schedule.cron_id.nextcall, before)
        self.assertEqual(schedule.cron_id.name, 'AI Schedule: Renamed Schedule')

    def test_toggling_active_mirrors_to_cron_without_moving_nextcall(self):
        schedule = self._make_schedule()
        before = schedule.cron_id.nextcall
        schedule.write({'active': False})
        self.assertFalse(schedule.cron_id.sudo().active)
        schedule.write({'active': True})
        self.assertTrue(schedule.cron_id.sudo().active)
        self.assertEqual(schedule.cron_id.nextcall, before)

    def test_changing_cadence_moves_nextcall(self):
        schedule = self._make_schedule(interval_type='days', interval_number=1)
        before = schedule.cron_id.nextcall
        schedule.write({'interval_type': 'hours', 'interval_number': 2})
        self.assertLess(schedule.cron_id.nextcall, before)

    # ----------------------------------------------------------
    # Tests Recurrence Validation
    # ----------------------------------------------------------

    def test_invalid_cron_expression_is_rejected_on_create(self):
        with self.assertRaises(ValidationError):
            self._make_schedule(
                interval_type='cron',
                cron_expression='not a cron',
            )

    def test_invalid_cron_expression_is_rejected_on_write(self):
        schedule = self._make_schedule()
        nextcall = schedule.cron_id.nextcall
        with self.assertRaises(ValidationError), self.cr.savepoint():
            schedule.write(
                {'interval_type': 'cron', 'cron_expression': '* * * *'},
            )
        self.env.invalidate_all()
        self.assertEqual(schedule.interval_type, 'days')
        self.assertEqual(schedule.cron_id.nextcall, nextcall)

    def test_weeks_without_weekday_is_rejected(self):
        with self.assertRaises(ValidationError):
            self._make_schedule(interval_type='weeks', weekday=False)

    def test_months_without_monthday_is_rejected(self):
        with self.assertRaises(ValidationError):
            self._make_schedule(interval_type='months', monthday=0)

    # ----------------------------------------------------------
    # Tests Owned Cron Reschedule
    # ----------------------------------------------------------

    def _make_job_snapshot(
        self, cron: models.BaseModel, nextcall: datetime | None = None
    ) -> dict:
        """Build the job dict that ir.cron._reschedule_later expects.

        :param nextcall: the job's due time; defaults to the cron's own
        """
        return {
            'id': cron.id,
            'nextcall': nextcall or cron.nextcall,
            'interval_type': cron.interval_type,
            'interval_number': cron.interval_number,
        }

    def _set_nextcall(
        self, schedule: models.BaseModel, nextcall: datetime
    ) -> models.BaseModel:
        """Pin the owned cron's next fire time and flush it to the database.

        ``ir.cron._reschedule_later`` rewrites ``nextcall`` with raw SQL, so a
        pending ORM write would otherwise be flushed afterwards and clobber it.

        :return: the schedule's owned cron, as superuser
        """
        cron = schedule.cron_id.sudo()
        cron.nextcall = nextcall
        self.env.flush_all()
        return cron

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
        cron = self._set_nextcall(schedule, datetime(2026, 2, 28, 9, 0))
        job = self._make_job_snapshot(cron)
        with freeze_time('2026-02-28 09:00:05'):
            self.env['ir.cron']._reschedule_later(job)
        cron.invalidate_recordset(['nextcall'])
        self.assertEqual(
            (cron.nextcall.year, cron.nextcall.month, cron.nextcall.day),
            (2026, 3, 31),
        )

    def test_reschedule_later_leaves_a_daily_cron_to_the_base_advance(self):
        schedule = self._make_schedule(interval_type='days', interval_number=1)
        cron = self._set_nextcall(schedule, datetime(2026, 3, 1, 9, 0))
        self.env['ir.cron']._reschedule_later(self._make_job_snapshot(cron))
        cron.invalidate_recordset(['nextcall'])
        self.assertGreater(cron.nextcall, self.env.cr.now())
        self.assertEqual((cron.nextcall.hour, cron.nextcall.minute), (9, 0))

    def test_reschedule_later_keeps_a_weekly_cron_on_its_weekday(self):
        schedule = self._make_schedule(
            interval_type='weeks',
            interval_number=1,
            weekday='mon',
        )
        cron = self._set_nextcall(schedule, datetime(2026, 3, 2, 9, 0))
        self.env['ir.cron']._reschedule_later(self._make_job_snapshot(cron))
        cron.invalidate_recordset(['nextcall'])
        self.assertGreater(cron.nextcall, self.env.cr.now())
        self.assertEqual(cron.nextcall.weekday(), 0)
        self.assertEqual((cron.nextcall.hour, cron.nextcall.minute), (9, 0))

    def test_cron_expression_nextcall_stays_utc_for_a_non_utc_owner(self):
        owner = new_test_user(
            self.env,
            login='ai_sched_tz_owner',
            groups='base.group_user',
            tz='Australia/Sydney',
        )
        schedule = self._make_schedule(
            interval_type='cron',
            cron_expression='0 9 * * *',
            user_id=owner.id,
        )
        with freeze_time('2026-03-01 12:00:00'):
            schedule._recompute_next_call_on_cron()
        nextcall = schedule.cron_id.sudo().nextcall
        self.assertEqual(nextcall, datetime(2026, 3, 2, 9, 0))

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

    def test_pickup_is_capped_and_prefers_the_oldest_due_sessions(self):
        now = fields.Datetime.now()
        sessions = []
        for offset in (5, 15, 25):
            session = self.Session.create(
                {
                    'name': 'Waiting %s' % offset,
                    'agent_id': self.agent.id,
                }
            )
            session.write(
                {
                    'state': 'schedule',
                    'resume_at': now - timedelta(minutes=offset),
                }
            )
            sessions.append(session)
        self.env.flush_all()
        with patch.object(ai_session, 'SCHEDULE_PICKUP_LIMIT', 2):
            ids = self.Session._find_pending_session_ids()
        self.assertIn(sessions[2].id, ids)
        self.assertIn(sessions[1].id, ids)
        self.assertNotIn(sessions[0].id, ids)
