from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install', 'muk_ai_schedule')
class TestScheduleTools(TransactionCase):

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.agent = cls.env['muk_ai.agent'].create({
            'name': 'Schedule Tools Agent',
        })
        cls.Session = cls.env['muk_ai.session']
        cls.Mixin = cls.env['muk_mcp.mixin']
        cls.Schedule = cls.env['muk_ai.schedule']

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _make_session(self, **vals):
        defaults = {
            'name': 'Tools Test Session',
            'agent_id': self.agent.id,
        }
        defaults.update(vals)
        return self.Session.create(defaults)

    def _make_schedule(self, **vals):
        defaults = {
            'name': 'Tools Test Schedule',
            'agent_id': self.agent.id,
            'prompt': 'Hello.',
            'interval_type': 'days',
            'interval_number': 1,
            'dispatch_mode': 'single',
        }
        defaults.update(vals)
        return self.Schedule.create(defaults)

    def _mixin_for(self, session):
        return self.Mixin.with_context(muk_mcp_session_id=session.id)

    # ----------------------------------------------------------
    # Tests schedule_resume
    # ----------------------------------------------------------

    def test_schedule_resume_seconds_from_now_sets_resume_at(self):
        session = self._make_session()
        before = fields.Datetime.now()
        result = self._mixin_for(session)._mcp_schedule_resume(
            seconds_from_now=120, prompt='ping',
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
            at=target_str, prompt='ping',
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
                seconds_from_now=10, prompt='ping',
            )

    def test_schedule_resume_max_delay_violation(self):
        session = self._make_session()
        with self.assertRaises(UserError):
            self._mixin_for(session)._mcp_schedule_resume(
                seconds_from_now=99_999_999, prompt='ping',
            )

    def test_schedule_resume_requires_session_context(self):
        with self.assertRaises(UserError):
            self.Mixin._mcp_schedule_resume(
                seconds_from_now=120, prompt='ping',
            )

    # ----------------------------------------------------------
    # Tests schedule_recurring
    # ----------------------------------------------------------

    def test_schedule_recurring_persists_config(self):
        session = self._make_session()
        result = self._mixin_for(session)._mcp_schedule_recurring(
            every=120, max_runs=3, prompt='ping',
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
        session.write({
            'recur_config': {
                'every': 120,
                'max_runs': 3,
                'started_at': fields.Datetime.to_string(fields.Datetime.now()),
                'prompt': 'ping',
            },
            'recur_runs_done': 3,
        })
        result = self._mixin_for(session)._mcp_schedule_recurring(
            every=120, max_runs=3, prompt='ping',
        )
        self.assertFalse(result['ok'])
        self.assertEqual(result['cap'], 'recur_max_runs')
        self.assertEqual(session.state, 'error')
        events = self.env['muk_ai.session.event'].search([
            ('session_id', '=', session.id),
            ('kind', '=', 'cap_exceeded'),
        ])
        self.assertEqual(len(events), 1)

    def test_schedule_recurring_rejects_both_until_and_max_runs(self):
        session = self._make_session()
        future = fields.Datetime.to_string(
            fields.Datetime.now() + timedelta(days=1)
        )
        with self.assertRaises(UserError):
            self._mixin_for(session)._mcp_schedule_recurring(
                every=120, until=future, max_runs=3, prompt='ping',
            )

    def test_schedule_recurring_rejects_neither_until_nor_max_runs(self):
        session = self._make_session()
        with self.assertRaises(UserError):
            self._mixin_for(session)._mcp_schedule_recurring(
                every=120, prompt='ping',
            )

    # ----------------------------------------------------------
    # Tests Cap Exceeded
    # ----------------------------------------------------------

    def test_cap_exceeded_posts_event(self):
        schedule = self._make_schedule(max_resumes=2)
        session = self._make_session(schedule_id=schedule.id)
        session.write({'recur_runs_done': 5})
        result = self._mixin_for(session)._mcp_schedule_resume(
            seconds_from_now=120, prompt='ping',
        )
        self.assertFalse(result['ok'])
        self.assertEqual(result['cap'], 'max_resumes')
        self.assertEqual(session.state, 'error')
        events = self.env['muk_ai.session.event'].search([
            ('session_id', '=', session.id),
            ('kind', '=', 'cap_exceeded'),
        ])
        self.assertEqual(len(events), 1)
        self.assertEqual(events.payload.get('cap'), 'max_resumes')

    # ----------------------------------------------------------
    # Tests Cron Pickup
    # ----------------------------------------------------------

    def test_resume_then_cron_picks_up(self):
        session = self._make_session()
        self._mixin_for(session)._mcp_schedule_resume(
            seconds_from_now=120, prompt='ping',
        )
        self.assertEqual(session.state, 'schedule')
        session.write({
            'resume_at': fields.Datetime.now() - timedelta(minutes=1),
        })
        self.env.flush_all()
        ids = self.Session._find_pending_session_ids()
        self.assertIn(session.id, ids)
