from __future__ import annotations

from odoo import models
from odoo.tests.common import tagged

from .common import ScheduleTestCommon
from odoo.addons.muk_ai_automation.tools.dispatch import _resolve_records


@tagged('post_install', '-at_install', 'muk_ai_schedule')
class TestScheduleFire(ScheduleTestCommon):
    """Covers single and per-record dispatch, record sources, and fire actions."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.partners = cls._make_partners(6, prefix='Dispatch Partner')

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _fire(self, schedule: models.BaseModel) -> models.BaseModel:
        """Fire ``schedule`` and return the sessions newly spawned by it."""
        before_ids = set(
            self.env['muk_ai.session']
            .search(
                [('schedule_id', '=', schedule.id)],
            )
            .ids
        )
        schedule.action_fire_now()
        return self.env['muk_ai.session'].search(
            [
                ('schedule_id', '=', schedule.id),
                ('id', 'not in', list(before_ids)),
            ],
            order='id',
        )

    # ----------------------------------------------------------
    # Tests Single Mode
    # ----------------------------------------------------------

    def test_single_dispatch_creates_one_session(self):
        schedule = self._make_schedule()
        with self._mock_provider():
            sessions = self._fire(schedule)
        self.assertEqual(len(sessions), 1)
        session = sessions
        self.assertEqual(session.schedule_id, schedule)
        self.assertFalse(session.previous_session_id)
        self.assertFalse(session.res_model)
        self.assertFalse(session.res_id)

    def test_per_record_session_injects_linked_record_tag(self):
        partner = self.partners[0]
        schedule = self._make_schedule(
            model_id=self.partner_model.id,
            domain=self._domain_for(partner),
            dispatch_mode='per_record',
        )
        with self._mock_provider():
            sessions = self._fire(schedule)
        self.assertEqual(len(sessions), 1)
        session = sessions
        self.assertEqual(session.res_model, 'res.partner')
        self.assertEqual(session.res_id, partner.id)
        inputs = session._build_request_inputs()
        last = inputs[-1]
        text = last['content'][0]['text']
        self.assertIn('<linked_record>', text)
        self.assertIn('res.partner', text)
        self.assertIn(str(partner.id), text)

    def test_single_dispatch_with_domain_exposes_records(self):
        partners = self.partners[:3]
        schedule = self._make_schedule(
            model_id=self.partner_model.id,
            domain=self._domain_for(partners),
            prompt='Count: {{ len(records) }}.',
        )
        with self._mock_provider():
            sessions = self._fire(schedule)
        self.assertEqual(len(sessions), 1)
        session = sessions
        user_turn = next(
            (e for e in session.conversation if e.get('role') == 'user'),
            None,
        )
        self.assertIsNotNone(user_turn)
        rendered_text = user_turn['content'][0]['text']
        self.assertEqual(rendered_text, 'Count: 3.')

    # ----------------------------------------------------------
    # Tests Per Record Mode
    # ----------------------------------------------------------

    def test_per_record_dispatch_caps_at_max(self):
        schedule = self._make_schedule(
            dispatch_mode='per_record',
            model_id=self.partner_model.id,
            domain=self._domain_for(self.partners),
            max_records_per_fire=3,
        )
        with self._mock_provider():
            sessions = self._fire(schedule)
        self.assertEqual(len(sessions), 3)

    def test_per_record_dispatch_chains_previous_session_id(self):
        partners = self.partners[:2]
        schedule = self._make_schedule(
            dispatch_mode='per_record',
            model_id=self.partner_model.id,
            domain=self._domain_for(partners),
            max_records_per_fire=10,
        )
        with self._mock_provider():
            first = self._fire(schedule)
        first_by_partner = {s.res_id: s for s in first}
        with self._mock_provider():
            second = self._fire(schedule)
        self.assertEqual(len(second), 2)
        for session in second:
            previous = first_by_partner.get(session.res_id)
            self.assertTrue(previous)
            self.assertEqual(session.previous_session_id, previous)

    def test_per_record_dispatch_sets_res_model_and_res_id(self):
        partners = self.partners[:2]
        schedule = self._make_schedule(
            dispatch_mode='per_record',
            model_id=self.partner_model.id,
            domain=self._domain_for(partners),
            max_records_per_fire=10,
        )
        with self._mock_provider():
            sessions = self._fire(schedule)
        self.assertEqual(len(sessions), 2)
        seen_ids = sorted(s.res_id for s in sessions)
        self.assertEqual(seen_ids, sorted(partners.ids))
        for session in sessions:
            self.assertEqual(session.res_model, 'res.partner')

    def test_per_record_dispatch_posts_chatter_mirror(self):
        partners = self.partners[:2]
        schedule = self._make_schedule(
            dispatch_mode='per_record',
            model_id=self.partner_model.id,
            domain=self._domain_for(partners),
            max_records_per_fire=10,
        )
        before = {p.id: len(p.message_ids) for p in partners}
        with self._mock_provider():
            self._fire(schedule)
        after = {p.id: len(p.message_ids) for p in partners.browse(partners.ids)}
        for pid in partners.ids:
            self.assertGreater(after[pid], before[pid])

    def test_empty_domain_returns_empty_recordset(self):
        schedule = self._make_schedule(
            dispatch_mode='per_record',
            model_id=self.partner_model.id,
            domain="[('id', '=', -1)]",
            max_records_per_fire=10,
        )
        with self._mock_provider():
            sessions = self._fire(schedule)
        self.assertFalse(sessions)

    # ----------------------------------------------------------
    # Tests Record Source: Python Code
    # ----------------------------------------------------------

    def test_record_source_code_resolves_recordset_for_single(self):
        partners = self.partners[:4]
        schedule = self._make_schedule(
            model_id=self.partner_model.id,
            record_source='code',
            record_code=(
                "records = env['res.partner'].search("
                "[('id', 'in', %s)], limit=2, order='id')"
            )
            % str(partners.ids),
            prompt='Got: {{ len(records) }}.',
        )
        with self._mock_provider():
            sessions = self._fire(schedule)
        self.assertEqual(len(sessions), 1)
        rendered = next(
            (e for e in sessions.conversation if e.get('role') == 'user'),
            None,
        )
        self.assertIsNotNone(rendered)
        self.assertEqual(rendered['content'][0]['text'], 'Got: 2.')

    def test_record_source_code_drives_per_record_fanout(self):
        partners = self.partners[:3]
        schedule = self._make_schedule(
            dispatch_mode='per_record',
            model_id=self.partner_model.id,
            record_source='code',
            record_code=("records = env['res.partner'].browse(%s)") % str(partners.ids),
            max_records_per_fire=10,
        )
        with self._mock_provider():
            sessions = self._fire(schedule)
        self.assertEqual(len(sessions), 3)
        self.assertEqual(
            sorted(s.res_id for s in sessions),
            sorted(partners.ids),
        )

    def test_record_source_code_syntax_error_returns_empty(self):
        schedule = self._make_schedule(
            model_id=self.partner_model.id,
            record_source='code',
            record_code='this is not valid python <<<',
        )
        records = _resolve_records(schedule.action_server_id)
        self.assertEqual(len(records), 0)
        self.assertEqual(records._name, 'res.partner')

    def test_record_source_code_wrong_type_returns_empty(self):
        schedule = self._make_schedule(
            model_id=self.partner_model.id,
            record_source='code',
            record_code='records = [1, 2, 3]',
        )
        records = _resolve_records(schedule.action_server_id)
        self.assertEqual(len(records), 0)
        self.assertEqual(records._name, 'res.partner')

    def test_record_source_code_blank_returns_empty(self):
        schedule = self._make_schedule(
            model_id=self.partner_model.id,
            record_source='code',
            record_code='   ',
        )
        records = _resolve_records(schedule.action_server_id)
        self.assertEqual(len(records), 0)
        self.assertEqual(records._name, 'res.partner')

    def test_record_source_code_relativedelta_in_context(self):
        recent = self.partners[:2]
        recent.write({'category_id': []})
        schedule = self._make_schedule(
            model_id=self.partner_model.id,
            record_source='code',
            record_code=(
                'cutoff = (now - relativedelta(years=10)).isoformat()\n'
                "records = env['res.partner'].search("
                "[('id', 'in', %s), ('write_date', '>=', cutoff)])"
            )
            % str(recent.ids),
            prompt='Got: {{ len(records) }}.',
        )
        with self._mock_provider():
            sessions = self._fire(schedule)
        rendered = next(
            (e for e in sessions.conversation if e.get('role') == 'user'),
            None,
        )
        self.assertEqual(rendered['content'][0]['text'], 'Got: 2.')

    # ----------------------------------------------------------
    # Tests Action
    # ----------------------------------------------------------

    def test_action_fire_now_wires_to_dispatch(self):
        schedule = self._make_schedule()
        before_count = self.env['muk_ai.session'].search_count(
            [('schedule_id', '=', schedule.id)],
        )
        with self._mock_provider():
            action = schedule.action_fire_now()
        after_count = self.env['muk_ai.session'].search_count(
            [('schedule_id', '=', schedule.id)],
        )
        self.assertGreaterEqual(after_count - before_count, 1)
        self.assertEqual(action['type'], 'ir.actions.act_window')

    def test_action_fire_now_owner_opens_chat(self):
        admin = self.env.ref('base.user_admin')
        schedule = self._make_schedule()
        with self._mock_provider():
            action = schedule.with_user(admin).action_fire_now()
        spawned = self.env['muk_ai.session'].search(
            [('schedule_id', '=', schedule.id)],
            limit=1,
        )
        self.assertEqual(spawned.user_id, admin)
        self.assertEqual(action['type'], 'ir.actions.client')

    def test_action_fire_now_per_record_returns_act_window(self):
        partners = self.partners[:2]
        schedule = self._make_schedule(
            dispatch_mode='per_record',
            model_id=self.partner_model.id,
            domain=self._domain_for(partners),
            max_records_per_fire=10,
        )
        with self._mock_provider():
            action = schedule.action_fire_now()
        self.assertEqual(action['type'], 'ir.actions.act_window')
        self.assertEqual(action['res_model'], 'muk_ai.session')

    # ----------------------------------------------------------
    # Tests Render Failure
    # ----------------------------------------------------------

    def test_render_failure_posts_prompt_render_error_event(self):
        schedule = self._make_schedule(
            prompt='Broken {{ undefined_var.x }}.',
        )
        with self._mock_provider():
            sessions = self._fire(schedule)
        self.assertEqual(len(sessions), 1)
        events = self.env['muk_ai.session.event'].search(
            [
                ('session_id', '=', sessions.id),
                ('kind', '=', 'prompt_render_error'),
            ]
        )
        self.assertEqual(len(events), 1)
        self.assertIn('error', events.payload)

    # ----------------------------------------------------------
    # Tests Recurrence
    # ----------------------------------------------------------

    def test_recompute_next_call_after_fire(self):
        schedule = self._make_schedule(
            interval_type='hours',
            interval_number=2,
        )
        with self._mock_provider():
            self._fire(schedule)
        self.assertTrue(schedule.last_call)
        self.assertTrue(schedule.next_call)
        delta = (schedule.next_call - schedule.last_call).total_seconds()
        self.assertAlmostEqual(delta, 2 * 3600, delta=2)
