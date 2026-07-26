from __future__ import annotations

from datetime import timedelta

from odoo import fields, models
from odoo.exceptions import UserError
from odoo.tests.common import tagged

from .common import ScheduleTestCommon


@tagged('post_install', '-at_install', 'muk_ai_schedule', 'test_prompt_injection')
class TestPromptInjection(ScheduleTestCommon):
    """Covers resume-prompt validation, persistence, and reactivation injection."""

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _user_messages(self, session: models.BaseModel) -> models.BaseModel:
        """Return the ordered user-message events of ``session``."""
        return self.Event.search(
            [
                ('session_id', '=', session.id),
                ('kind', '=', 'user_message'),
            ],
            order='sequence',
        )

    # ----------------------------------------------------------
    # Tests Validation
    # ----------------------------------------------------------

    def test_resume_rejects_empty_prompt(self):
        session = self._make_session()
        with self.assertRaises(UserError):
            self._mixin_for(session)._mcp_schedule_resume(
                seconds_from_now=120,
                prompt='',
            )

    def test_resume_rejects_whitespace_prompt(self):
        session = self._make_session()
        with self.assertRaises(UserError):
            self._mixin_for(session)._mcp_schedule_resume(
                seconds_from_now=120,
                prompt='   ',
            )

    def test_resume_rejects_oversized_prompt(self):
        session = self._make_session()
        oversized = 'x' * 4001
        with self.assertRaises(UserError):
            self._mixin_for(session)._mcp_schedule_resume(
                seconds_from_now=120,
                prompt=oversized,
            )

    # ----------------------------------------------------------
    # Tests Persistence
    # ----------------------------------------------------------

    def test_recur_stores_prompt_in_config(self):
        session = self._make_session()
        result = self._mixin_for(session)._mcp_schedule_recurring(
            every=120,
            max_runs=3,
            prompt='Run {run}/{total}',
        )
        self.assertTrue(result['ok'])
        self.assertEqual(
            (session.recur_config or {}).get('prompt'),
            'Run {run}/{total}',
        )

    # ----------------------------------------------------------
    # Tests Reactivation
    # ----------------------------------------------------------

    def test_reactivation_injects_user_message(self):
        session = self._make_session()
        session.write(
            {
                'state': 'schedule',
                'resume_at': fields.Datetime.now() - timedelta(minutes=1),
                'resume_prompt': 'hi',
            }
        )
        before = len(self._user_messages(session))
        self.Session._reactivate_due_schedules()
        messages = self._user_messages(session)
        self.assertEqual(len(messages), before + 1)
        injected = messages[-1]
        self.assertEqual(injected.payload.get('content'), 'hi')
        self.assertEqual(session.state, 'running')
        self.assertFalse(session.resume_at)

    def test_run_total_placeholders_render(self):
        session = self._make_session()
        session.write(
            {
                'state': 'schedule',
                'resume_at': fields.Datetime.now() - timedelta(minutes=1),
                'recur_config': {
                    'every': 60,
                    'max_runs': 5,
                    'prompt': 'Run {run} of {total}',
                    'started_at': fields.Datetime.to_string(fields.Datetime.now()),
                },
                'recur_runs_done': 3,
            }
        )
        self.Session._reactivate_due_schedules()
        injected = self._user_messages(session)[-1]
        self.assertEqual(injected.payload.get('content'), 'Run 3 of 5')

    def test_stray_braces_preserved(self):
        session = self._make_session()
        session.write(
            {
                'state': 'schedule',
                'resume_at': fields.Datetime.now() - timedelta(minutes=1),
                'resume_prompt': 'Check {orderId}',
            }
        )
        self.Session._reactivate_due_schedules()
        injected = self._user_messages(session)[-1]
        self.assertEqual(injected.payload.get('content'), 'Check {orderId}')

    def test_resume_prompt_cleared_after_consumption(self):
        session = self._make_session()
        session.write(
            {
                'state': 'schedule',
                'resume_at': fields.Datetime.now() - timedelta(minutes=1),
                'resume_prompt': 'one shot',
            }
        )
        self.Session._reactivate_due_schedules()
        self.assertFalse(session.resume_prompt)

    def test_recur_prompt_persists_across_fires(self):
        session = self._make_session()
        session.write(
            {
                'state': 'schedule',
                'resume_at': fields.Datetime.now() - timedelta(minutes=1),
                'recur_config': {
                    'every': 60,
                    'max_runs': 5,
                    'prompt': 'Run {run} of {total}',
                    'started_at': fields.Datetime.to_string(fields.Datetime.now()),
                },
                'recur_runs_done': 1,
            }
        )
        self.Session._reactivate_due_schedules()
        first = self._user_messages(session)[-1]
        self.assertEqual(first.payload.get('content'), 'Run 1 of 5')
        self.assertEqual(
            (session.recur_config or {}).get('prompt'),
            'Run {run} of {total}',
        )
        session.write(
            {
                'state': 'schedule',
                'resume_at': fields.Datetime.now() - timedelta(minutes=1),
                'recur_runs_done': 2,
            }
        )
        self.Session._reactivate_due_schedules()
        second = self._user_messages(session)[-1]
        self.assertEqual(second.payload.get('content'), 'Run 2 of 5')
