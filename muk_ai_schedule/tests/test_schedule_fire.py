from contextlib import contextmanager
from unittest.mock import patch

from odoo.tests.common import TransactionCase, tagged

from odoo.addons.muk_ai_schedule.tools.dispatch import _resolve_records, fire_schedule


@tagged('post_install', '-at_install', 'muk_ai_schedule')
class TestScheduleFire(TransactionCase):

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.provider = cls.env.ref('muk_ai.provider_openai')
        cls.provider.sudo().api_key = 'test-key'
        cls.env.company.default_ai_provider_id = cls.provider
        cls.partner_model = cls.env['ir.model']._get('res.partner')
        cls.agent = cls.env['muk_ai.agent'].create({
            'name': 'Schedule Dispatch Agent',
        })
        cls.partners = cls.env['res.partner'].create([
            {'name': 'Dispatch Partner %d' % i} for i in range(6)
        ])

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @contextmanager
    def _mock_provider(self, text='ok'):
        payload = {
            'text': text,
            'tool_calls': [],
            'carry_inputs': [],
            'usage': {'input_tokens': 1, 'output_tokens': 1, 'cached_tokens': 0},
        }

        def fake(self_arg, *args, **kwargs):
            return payload

        with patch.object(
            type(self.provider),
            '_request_responses',
            autospec=True,
            side_effect=fake,
        ) as mock:
            yield mock

    def _make_schedule(self, **vals):
        defaults = {
            'name': 'Dispatch Schedule',
            'agent_id': self.agent.id,
            'prompt': 'Hello.',
            'interval_type': 'days',
            'interval_number': 1,
            'dispatch_mode': 'single',
        }
        defaults.update(vals)
        return self.env['muk_ai.schedule'].create(defaults)

    def _domain_for(self, partners):
        return "[('id', 'in', %s)]" % str(partners.ids)

    # ----------------------------------------------------------
    # Tests Single Mode
    # ----------------------------------------------------------

    def test_single_dispatch_creates_one_session(self):
        schedule = self._make_schedule()
        with self._mock_provider():
            sessions = fire_schedule(schedule)
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
            sessions = fire_schedule(schedule)
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
            sessions = fire_schedule(schedule)
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
            sessions = fire_schedule(schedule)
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
            first = fire_schedule(schedule)
        first_by_partner = {s.res_id: s for s in first}
        with self._mock_provider():
            second = fire_schedule(schedule)
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
            sessions = fire_schedule(schedule)
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
            fire_schedule(schedule)
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
            sessions = fire_schedule(schedule)
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
            ) % str(partners.ids),
            prompt='Got: {{ len(records) }}.',
        )
        with self._mock_provider():
            sessions = fire_schedule(schedule)
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
            record_code=(
                "records = env['res.partner'].browse(%s)"
            ) % str(partners.ids),
            max_records_per_fire=10,
        )
        with self._mock_provider():
            sessions = fire_schedule(schedule)
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
        records = _resolve_records(schedule)
        self.assertEqual(len(records), 0)
        self.assertEqual(records._name, 'res.partner')

    def test_record_source_code_wrong_type_returns_empty(self):
        schedule = self._make_schedule(
            model_id=self.partner_model.id,
            record_source='code',
            record_code="records = [1, 2, 3]",
        )
        records = _resolve_records(schedule)
        self.assertEqual(len(records), 0)
        self.assertEqual(records._name, 'res.partner')

    def test_record_source_code_blank_returns_empty(self):
        schedule = self._make_schedule(
            model_id=self.partner_model.id,
            record_source='code',
            record_code='   ',
        )
        records = _resolve_records(schedule)
        self.assertEqual(len(records), 0)
        self.assertEqual(records._name, 'res.partner')

    def test_record_source_code_relativedelta_in_context(self):
        recent = self.partners[:2]
        recent.write({'category_id': []})
        schedule = self._make_schedule(
            model_id=self.partner_model.id,
            record_source='code',
            record_code=(
                "cutoff = (now - relativedelta(years=10)).isoformat()\n"
                "records = env['res.partner'].search("
                "[('id', 'in', %s), ('write_date', '>=', cutoff)])"
            ) % str(recent.ids),
            prompt='Got: {{ len(records) }}.',
        )
        with self._mock_provider():
            sessions = fire_schedule(schedule)
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
            sessions = fire_schedule(schedule)
        self.assertEqual(len(sessions), 1)
        events = self.env['muk_ai.session.event'].search([
            ('session_id', '=', sessions.id),
            ('kind', '=', 'prompt_render_error'),
        ])
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
            fire_schedule(schedule)
        self.assertTrue(schedule.last_call)
        self.assertTrue(schedule.next_call)
        delta = (schedule.next_call - schedule.last_call).total_seconds()
        self.assertAlmostEqual(delta, 2 * 3600, delta=2)
