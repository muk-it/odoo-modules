from __future__ import annotations

from datetime import datetime, timedelta

from odoo import fields, models
from odoo.tests import tagged

from .common import ScheduleTestCommon


@tagged('post_install', '-at_install', 'muk_ai_schedule')
class TestPromptRender(ScheduleTestCommon):
    """Covers prompt evaluation context, previous-session proxy, and fallbacks."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.partner = cls.env.ref('base.partner_admin')

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _make_linked_schedule(self, **vals) -> models.BaseModel:
        """Create a schedule targeting the fixture partner."""
        defaults = {
            'model_id': self.partner_model.id,
            'domain': "[('id', '=', %d)]" % self.partner.id,
        }
        defaults.update(vals)
        return self._make_schedule(**defaults)

    # ----------------------------------------------------------
    # Tests Eval Context
    # ----------------------------------------------------------

    def test_eval_context_binds_the_linked_record_and_now(self):
        session = self._make_session(
            res_model='res.partner',
            res_id=self.partner.id,
        )
        before = fields.Datetime.now()
        extras = session._session_prompt_extras()
        self.assertEqual(extras['record'], self.partner)
        self.assertFalse(extras['records'])
        self.assertEqual(extras['previous_session'].last_text, '')
        self.assertIsInstance(extras['now'], datetime)
        self.assertLess(abs(extras['now'] - before), timedelta(minutes=1))

    def test_record_resolves_to_browse_singleton(self):
        session = self._make_session(
            res_model='res.partner',
            res_id=self.partner.id,
        )
        rendered = session._render_system_prompt('Hello {{ record.name }}.')
        self.assertTrue(rendered.startswith('Hello %s.' % self.partner.name))

    def test_record_empty_when_no_link(self):
        session = self._make_session()
        extras = session._session_prompt_extras()
        self.assertFalse(extras['record'])

    def test_records_resolves_to_search_domain(self):
        schedule = self._make_linked_schedule()
        session = self._make_session(schedule_id=schedule.id)
        domain = [('id', '=', self.partner.id)]
        expected = self.env['res.partner'].search_count(domain)
        rendered = session._render_system_prompt('Count: {{ len(records) }}.')
        self.assertEqual(rendered, 'Count: %d.' % expected)

    def test_records_empty_when_per_record_dispatch(self):
        schedule = self._make_linked_schedule(dispatch_mode='per_record')
        session = self._make_session(
            schedule_id=schedule.id,
            res_model='res.partner',
            res_id=self.partner.id,
        )
        extras = session._session_prompt_extras()
        self.assertFalse(extras['records'])

    # ----------------------------------------------------------
    # Tests Previous Session Proxy
    # ----------------------------------------------------------

    def test_previous_session_proxy_empty(self):
        session = self._make_session()
        rendered = session._render_system_prompt(
            'Last: [{{ previous_session.last_text }}]',
        )
        self.assertEqual(rendered, 'Last: []')

    def test_previous_session_proxy_populated(self):
        previous = self._make_session()
        previous.last_text = 'Prior summary'
        session = self._make_session(previous_session_id=previous.id)
        rendered = session._render_system_prompt(
            'Last: {{ previous_session.last_text }}.',
        )
        self.assertEqual(rendered, 'Last: Prior summary.')

    # ----------------------------------------------------------
    # Tests Render Failure Fallback
    # ----------------------------------------------------------

    def test_render_failure_falls_back_to_raw(self):
        session = self._make_session()
        raw = 'Value is {{ undefined_var.attribute }}.'
        rendered = session._render_system_prompt(raw)
        self.assertEqual(rendered, raw)

    def test_schedule_render_failure_falls_back_to_raw(self):
        raw = 'Value is {{ undefined_var.attribute }}.'
        schedule = self._make_linked_schedule(prompt=raw)
        rendered, _error = schedule._build_prompt()
        self.assertEqual(rendered, raw)
