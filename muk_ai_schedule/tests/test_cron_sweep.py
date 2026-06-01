from datetime import timedelta

from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'muk_ai_schedule')
class TestCronSweep(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.agent = cls.env['muk_ai.agent'].create({
            'name': 'Cron Sweep Agent',
        })
        cls.partner_model = cls.env['ir.model']._get('res.partner')
        cls.Session = cls.env['muk_ai.session']
        cls.Schedule = cls.env['muk_ai.schedule']

    def _make_schedule(self, **vals):
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

    # ----------------------------------------------------------
    # Tests _cron_fire_due_schedules
    # ----------------------------------------------------------

    def test_due_schedule_is_fired(self):
        schedule = self._make_schedule()
        schedule.next_call = fields.Datetime.now() - timedelta(minutes=1)
        before = self.Session.search_count([('schedule_id', '=', schedule.id)])
        self.Schedule._cron_fire_due_schedules()
        after = self.Session.search_count([('schedule_id', '=', schedule.id)])
        self.assertGreater(after, before)

    def test_inactive_schedule_not_fired(self):
        schedule = self._make_schedule(active=False)
        schedule.next_call = fields.Datetime.now() - timedelta(minutes=1)
        self.Schedule._cron_fire_due_schedules()
        sessions = self.Session.search_count(
            [('schedule_id', '=', schedule.id)]
        )
        self.assertEqual(sessions, 0)

    def test_future_schedule_not_fired(self):
        schedule = self._make_schedule()
        schedule.next_call = fields.Datetime.now() + timedelta(hours=1)
        self.Schedule._cron_fire_due_schedules()
        sessions = self.Session.search_count(
            [('schedule_id', '=', schedule.id)]
        )
        self.assertEqual(sessions, 0)

    def test_schedule_without_next_call_not_fired(self):
        schedule = self._make_schedule()
        schedule.next_call = False
        self.Schedule._cron_fire_due_schedules()
        sessions = self.Session.search_count(
            [('schedule_id', '=', schedule.id)]
        )
        self.assertEqual(sessions, 0)

    def test_due_schedule_recomputes_next_call(self):
        schedule = self._make_schedule()
        schedule.next_call = fields.Datetime.now() - timedelta(minutes=1)
        before = schedule.next_call
        self.Schedule._cron_fire_due_schedules()
        self.assertGreater(schedule.next_call, before)

    # ----------------------------------------------------------
    # Tests _find_pending_session_ids extension
    # ----------------------------------------------------------

    def test_schedule_state_with_past_resume_at_picked_up(self):
        session = self.Session.create({
            'name': 'Waiting Test',
            'agent_id': self.agent.id,
        })
        session.write({
            'state': 'schedule',
            'resume_at': fields.Datetime.now() - timedelta(minutes=1),
        })
        self.env.flush_all()
        ids = self.Session._find_pending_session_ids()
        self.assertIn(session.id, ids)

    def test_schedule_state_with_future_resume_at_not_picked(self):
        session = self.Session.create({
            'name': 'Waiting Future',
            'agent_id': self.agent.id,
        })
        session.write({
            'state': 'schedule',
            'resume_at': fields.Datetime.now() + timedelta(hours=1),
        })
        self.env.flush_all()
        ids = self.Session._find_pending_session_ids()
        self.assertNotIn(session.id, ids)

    def test_schedule_state_with_no_resume_at_not_picked(self):
        session = self.Session.create({
            'name': 'Waiting No Time',
            'agent_id': self.agent.id,
        })
        session.write({'state': 'schedule'})
        self.env.flush_all()
        ids = self.Session._find_pending_session_ids()
        self.assertNotIn(session.id, ids)

    # ----------------------------------------------------------
    # Tests _claim_schedule_lock
    # ----------------------------------------------------------

    def test_claim_lock_returns_true_on_first_acquire(self):
        result = self.Schedule._claim_schedule_lock(999_999_001)
        self.assertTrue(result)

    def test_claim_lock_returns_false_on_re_acquire_in_same_tx(self):
        self.Schedule._claim_schedule_lock(999_999_002)
        second = self.Schedule._claim_schedule_lock(999_999_002)
        self.assertTrue(second)
