from odoo.tests import TransactionCase, tagged

from odoo.addons.muk_ai_schedule.tools.dispatch import PreviousProxy


@tagged('post_install', '-at_install')
class TestPromptRender(TransactionCase):

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env.ref('base.partner_admin')
        cls.partner_model = cls.env['ir.model']._get('res.partner')
        cls.agent = cls.env['muk_ai.agent'].create({
            'name': 'Schedule Test Agent',
        })

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _make_session(self, **vals):
        defaults = {'name': 'Schedule Test Session'}
        defaults.update(vals)
        return self.env['muk_ai.session'].create(defaults)

    def _make_schedule(self, **vals):
        defaults = {
            'name': 'Test Schedule',
            'agent_id': self.agent.id,
            'prompt': 'Hello.',
            'interval_type': 'days',
            'interval_number': 1,
            'dispatch_mode': 'single',
            'model_id': self.partner_model.id,
            'domain': "[('id', '=', %d)]" % self.partner.id,
        }
        defaults.update(vals)
        return self.env['muk_ai.schedule'].create(defaults)

    # ----------------------------------------------------------
    # Tests Eval Context
    # ----------------------------------------------------------

    def test_eval_context_has_now_record_records_previous(self):
        session = self._make_session(
            res_model='res.partner',
            res_id=self.partner.id,
        )
        extras = session._session_prompt_extras()
        self.assertIn('now', extras)
        self.assertIn('record', extras)
        self.assertIn('records', extras)
        self.assertIn('previous_session', extras)

    def test_record_resolves_to_browse_singleton(self):
        session = self._make_session(
            res_model='res.partner',
            res_id=self.partner.id,
        )
        rendered = session._render_system_prompt('Hello {{ record.name }}.')
        self.assertEqual(rendered, 'Hello %s.' % self.partner.name)

    def test_record_empty_when_no_link(self):
        session = self._make_session()
        extras = session._session_prompt_extras()
        self.assertFalse(extras['record'])

    def test_records_resolves_to_search_domain(self):
        schedule = self._make_schedule()
        session = self._make_session(
            schedule_id=schedule.id,
        )
        domain = [('id', '=', self.partner.id)]
        expected = self.env['res.partner'].search_count(domain)
        rendered = session._render_system_prompt(
            'Count: {{ len(records) }}.',
        )
        self.assertEqual(rendered, 'Count: %d.' % expected)

    def test_records_empty_when_per_record_dispatch(self):
        schedule = self._make_schedule(dispatch_mode='per_record')
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
        session = self._make_session(
            previous_session_id=previous.id,
        )
        rendered = session._render_system_prompt(
            'Last: {{ previous_session.last_text }}.',
        )
        self.assertEqual(rendered, 'Last: Prior summary.')

    def test_previous_session_proxy_tool_log_empty(self):
        proxy = PreviousProxy(None)
        self.assertEqual(proxy.last_text, '')
        self.assertEqual(proxy.tool_log, [])

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
        schedule = self._make_schedule(prompt=raw)
        rendered, _ = schedule._build_prompt()
        self.assertEqual(rendered, raw)
