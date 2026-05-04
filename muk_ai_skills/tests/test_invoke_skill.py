from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install', 'muk_ai_skills', 'invoke')
class TestInvokeSkill(TransactionCase):

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Skill = cls.env['muk_ai.skill']
        cls.Session = cls.env['muk_ai.session']
        cls.Agent = cls.env['muk_ai.agent']
        cls.Mixin = cls.env['muk_mcp.mixin']
        cls.agent = cls.Agent.create({'name': 'Invoke Test Agent'})
        cls.other_agent = cls.Agent.create({'name': 'Invoke Test Other Agent'})

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _make_session(self, agent=None):
        return self.Session.create({
            'name': 'Invoke Test Session',
            'agent_id': (agent or self.agent).id,
        })

    def _make_skill(self, **vals):
        defaults = {
            'name': 'invoke_demo',
            'description': 'Demo invocation.',
            'body': 'Run the demo procedure.',
        }
        defaults.update(vals)
        return self.Skill.create(defaults)

    def _mixin_for(self, session):
        return self.Mixin.with_context(muk_mcp_session_id=session.id)

    def _drop_existing_skills(self):
        self.env['muk_ai.skill'].sudo().search([]).unlink()

    # ----------------------------------------------------------
    # Tests happy path
    # ----------------------------------------------------------

    def test_invoke_returns_body_and_manifest(self):
        self._drop_existing_skills()
        attachment = self.env['ir.attachment'].create({
            'name': 'cheatsheet.md',
            'datas': b'IyBDaGVhdHNoZWV0',
            'mimetype': 'text/markdown',
        })
        skill = self._make_skill(
            attachment_ids=[(6, 0, [attachment.id])],
        )
        session = self._make_session()
        result = self._mixin_for(session)._mcp_invoke_skill(skill_name=skill.name)
        self.assertEqual(result['name'], skill.name)
        self.assertEqual(result['body'], skill.body)
        self.assertEqual(len(result['resources']), 1)
        manifest = result['resources'][0]
        self.assertEqual(manifest['name'], 'cheatsheet.md')
        self.assertEqual(manifest['mimetype'], 'text/markdown')
        self.assertEqual(manifest['uri'], 'odoo://attachment/%d' % attachment.id)

    def test_invoke_empty_body_skill(self):
        self._drop_existing_skills()
        skill = self._make_skill(name='empty_skill', body=False)
        session = self._make_session()
        result = self._mixin_for(session)._mcp_invoke_skill(skill_name=skill.name)
        self.assertEqual(result['body'], '')
        self.assertEqual(result['resources'], [])

    # ----------------------------------------------------------
    # Tests error paths
    # ----------------------------------------------------------

    def test_invoke_missing_name_raises(self):
        session = self._make_session()
        with self.assertRaises(UserError):
            self._mixin_for(session)._mcp_invoke_skill(skill_name=None)

    def test_invoke_unknown_skill_raises(self):
        session = self._make_session()
        with self.assertRaises(UserError):
            self._mixin_for(session)._mcp_invoke_skill(skill_name='no_such_skill')

    def test_invoke_forbidden_skill_raises(self):
        self._drop_existing_skills()
        skill = self._make_skill(
            name='private_skill',
            agent_ids=[(6, 0, [self.other_agent.id])],
        )
        session = self._make_session(self.agent)
        with self.assertRaises(UserError):
            self._mixin_for(session)._mcp_invoke_skill(skill_name=skill.name)

    def test_invoke_requires_session_context(self):
        with self.assertRaises(UserError):
            self.Mixin._mcp_invoke_skill(skill_name='anything')

    # ----------------------------------------------------------
    # Tests slash dispatch
    # ----------------------------------------------------------

    def test_invoke_skill_from_chat_appends_events_and_conversation(self):
        self._drop_existing_skills()
        skill = self._make_skill(name='slash_demo', body='Slash body.')
        session = self._make_session()
        snapshot = session.invoke_skill_from_chat(skill.name)
        events = snapshot['events']
        kinds = [e.get('kind') for e in events]
        self.assertIn('tool_call', kinds)
        self.assertIn('tool_result', kinds)
        result_event = next(e for e in events if e.get('kind') == 'tool_result')
        self.assertEqual(result_event['name'], 'invoke_skill')
        self.assertEqual(result_event['result']['body'], 'Slash body.')
        conversation = session.conversation or []
        types = [item.get('type') for item in conversation]
        self.assertIn('function_call', types)
        self.assertIn('function_call_output', types)

    def test_invoke_skill_from_chat_unknown_raises(self):
        session = self._make_session()
        with self.assertRaises(UserError):
            session.invoke_skill_from_chat('not_a_skill')

    def test_invoke_skill_from_chat_forbidden_raises(self):
        self._drop_existing_skills()
        skill = self._make_skill(
            name='forbidden_slash',
            agent_ids=[(6, 0, [self.other_agent.id])],
        )
        session = self._make_session(self.agent)
        with self.assertRaises(UserError):
            session.invoke_skill_from_chat(skill.name)
