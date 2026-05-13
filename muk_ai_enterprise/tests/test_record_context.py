from odoo.tests.common import tagged

from .common import BridgeTestCommon


@tagged('post_install', '-at_install')
class TestRecordContext(BridgeTestCommon):

    def _make_session_with_record(self, model='res.users'):
        record = self.env[model].search([], limit=1)
        if not record:
            self.skipTest(f"No {model} record available.")
        agent = self.env['muk_ai.agent'].create({
            'name': 'Record Context Agent',
            'system_prompt': 'You are a record assistant.',
        })
        session = self.env['muk_ai.session'].create({
            'name': 'Record Session',
            'agent_id': agent.id,
        })
        session.set_view_context({
            'kind': 'record',
            'model': record._name,
            'id': record.id,
        })
        return session, record

    def test_record_view_context_gets_ee_init_context(self):
        session, record = self._make_session_with_record()
        vc = session.view_context or {}
        self.assertEqual(vc.get('kind'), 'record')
        self.assertEqual(vc.get('model'), record._name)
        self.assertEqual(vc.get('id'), record.id)
        self.assertIn(
            'ee_init_context', vc,
            "Bridge must populate ee_init_context for record kind.",
        )
        self.assertIsInstance(vc['ee_init_context'], list)
        self.assertTrue(vc['ee_init_context'])

    def test_non_record_view_context_unchanged(self):
        agent = self.env['muk_ai.agent'].create({'name': 'List Agent'})
        session = self.env['muk_ai.session'].create({
            'name': 'List Session',
            'agent_id': agent.id,
        })
        session.set_view_context({
            'kind': 'list',
            'model': 'res.users',
        })
        vc = session.view_context or {}
        self.assertEqual(vc.get('kind'), 'list')
        self.assertNotIn('ee_init_context', vc)

    def test_model_without_ai_init_context(self):
        agent = self.env['muk_ai.agent'].create({'name': 'Bare Model Agent'})
        session = self.env['muk_ai.session'].create({
            'name': 'Bare Model Session',
            'agent_id': agent.id,
        })
        users = self.env.ref('base.user_admin')
        session.set_view_context({
            'kind': 'record',
            'model': users._name,
            'id': users.id,
        })
        self.assertEqual(
            (session.view_context or {}).get('model'),
            users._name,
        )

    def test_rendered_prompt_contains_ee_context(self):
        session, _record = self._make_session_with_record()
        rendered = session._render_system_prompt(
            session.agent_id.system_prompt
        )
        vc = session.view_context or {}
        ee = vc.get('ee_init_context') or []
        if not ee:
            self.skipTest("No ee_init_context available for this record.")
        self.assertIn(ee[0][:30], rendered)
