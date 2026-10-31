from __future__ import annotations

import json

from odoo import models
from odoo.exceptions import UserError
from odoo.tests.common import tagged

from odoo.addons.muk_ai.tests.common import AITestCommon


@tagged('post_install', '-at_install', 'muk_ai_skills', 'invoke')
class TestInvokeSkill(AITestCommon):
    """Test the invoke_skill MCP tool and the slash-command dispatch."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
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

    def _make_session(self, agent: models.BaseModel | None = None) -> models.BaseModel:
        """Create an AI session bound to the given or default agent."""
        return self.Session.create(
            {
                'name': 'Invoke Test Session',
                'agent_id': (agent or self.agent).id,
            }
        )

    def _make_skill(self, **vals) -> models.BaseModel:
        """Create a skill record, overriding the defaults with ``vals``."""
        defaults = {
            'name': 'invoke_demo',
            'description': 'Demo invocation.',
            'body': 'Run the demo procedure.',
        }
        defaults.update(vals)
        return self.Skill.create(defaults)

    def _mixin_for(self, session: models.BaseModel) -> models.BaseModel:
        """Return the tools mixin bound to the given session context."""
        return self.Mixin.with_context(muk_mcp_session_id=session.id)

    def _drop_existing_skills(self) -> None:
        """Remove every existing skill to isolate the test fixtures."""
        self.env['muk_ai.skill'].sudo().search([]).unlink()

    # ----------------------------------------------------------
    # Tests happy path
    # ----------------------------------------------------------

    def test_invoke_returns_body_and_manifest(self):
        self._drop_existing_skills()
        attachment = self.env['ir.attachment'].create(
            {
                'name': 'cheatsheet.md',
                'datas': b'IyBDaGVhdHNoZWV0',
                'mimetype': 'text/markdown',
            }
        )
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

    def test_invoke_skill_from_chat_appends_events_and_runs_llm(self):
        self._drop_existing_skills()
        skill = self._make_skill(name='slash_demo', body='Slash body.')
        session = self._make_session()
        with self._mock_responses([self._make_text_response('Acknowledged.')]):
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
        self.assertEqual(session.state, 'done')
        self.assertEqual(session.last_text, 'Acknowledged.')

    def test_invoke_skill_from_chat_blocked_when_running(self):
        self._drop_existing_skills()
        skill = self._make_skill(name='blocked_slash', body='Slash body.')
        session = self._make_session()
        session.state = 'running'
        with self.assertRaises(UserError):
            session.invoke_skill_from_chat(skill.name)

    def test_a_slash_command_asks_runs_the_skill_then_replies(self):
        self._drop_existing_skills()
        skill = self._make_skill(name='args_slash', body='Body.')
        for user_input, asked, argument in (
            ('product xy', 'product xy', 'product xy'),
            ('   ', skill.display_name, None),
        ):
            with self.subTest(user_input=user_input):
                session = self._make_session()
                with self._mock_responses([self._make_text_response('ok')]):
                    snapshot = session.invoke_skill_from_chat(
                        skill.name, user_input=user_input
                    )
                self.assertEqual(session.name, skill.display_name)
                self.assertEqual(
                    [event.get('kind') for event in snapshot['events']][:3],
                    ['user_message', 'tool_call', 'tool_result'],
                )
                conversation = [
                    item
                    for item in session.conversation
                    if item.get('role') != 'system'
                ]
                self.assertEqual(conversation[0]['content'][0]['text'], asked)
                self.assertEqual(
                    [item.get('type') for item in conversation[1:3]],
                    ['function_call', 'function_call_output'],
                )
                self.assertEqual(
                    json.loads(conversation[1]['arguments']).get('user_input'),
                    argument,
                )

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

    def test_server_side_invoke_accepts_a_builtin_named_skill(self):
        self._drop_existing_skills()
        self._make_skill(name='help', body='Hijacked help body.')
        session = self._make_session()
        with self._mock_responses([self._make_text_response('ok')]):
            snapshot = session.invoke_skill_from_chat('help')
        result_event = next(
            event for event in snapshot['events'] if event.get('kind') == 'tool_result'
        )
        self.assertEqual(result_event['result']['name'], 'help')
        self.assertEqual(result_event['result']['body'], 'Hijacked help body.')

    def test_build_skill_call_id_is_prefixed_and_unique(self):
        session = self._make_session()
        first = session._build_skill_call_id('demo')
        second = session._build_skill_call_id('demo')
        self.assertTrue(first.startswith('slash_skill_demo_'))
        self.assertNotEqual(first, second)
