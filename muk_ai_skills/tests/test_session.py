from __future__ import annotations

import json

from odoo import Command, models
from odoo.exceptions import AccessError, UserError
from odoo.tests import new_test_user

from odoo.addons.muk_ai.tests.common import AITestCommon, text_payload, tool_payload


class TestSkillSession(AITestCommon):
    """Test skills inside a chat: the prompt, the tool, the slash command."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        """Start from no skill but one shared skill with a resource."""
        super().setUpClass()
        cls.env['muk_ai.skill'].search([]).unlink()
        cls.agent = cls.env['muk_ai.agent'].create({'name': 'Skill Agent'})
        cls.other_agent = cls.env['muk_ai.agent'].create({'name': 'Other Agent'})
        cls.resource = cls.env['ir.attachment'].create(
            {
                'name': 'cheatsheet.md',
                'raw': b'# Cheatsheet',
                'mimetype': 'text/markdown',
            }
        )
        cls.skill = cls._skill(
            name='demo',
            description='Do demo things.\nMore detail.',
            body='Run the demo procedure.',
            attachment_ids=[Command.set(cls.resource.ids)],
        )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @classmethod
    def _skill(cls, **values) -> models.BaseModel:
        """Create a skill shared with everyone, overriding defaults with ``values``."""
        return cls.env['muk_ai.skill'].create(
            {'description': 'A test skill.', 'user_ids': [Command.clear()], **values}
        )

    def _chat(self) -> models.BaseModel:
        """Create a chat with the test agent."""
        return self._session(agent_id=self.agent.id)

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_visible_skills_reach_the_prompt_and_load_the_tool(self):
        self._skill(name='chatty', scope='chatter')
        self._skill(name='hidden', agent_ids=[Command.set(self.other_agent.ids)])
        self._skill(name='retired', active=False)
        self._skill(name='scoped', agent_ids=[Command.set(self.agent.ids)])
        with self._mock_responses([text_payload()]) as requests:
            self._chat().send_message('hi')
        system = self._system_prompt(requests[0])
        self.assertIn('- `demo`: Do demo things.\n', system)
        self.assertIn(
            '- `chatty`: A test skill. (needs a record with a chatter open)', system
        )
        self.assertIn('`scoped`', system)
        self.assertNotIn('hidden', system)
        self.assertNotIn('retired', system)
        self.assertIn('invoke_skill', self._tools(requests[0]))
        self.assertIn('invoke_skill', self.agent._rule_governed_tool_names())
        unassigned = self._session(agent_id=False)._visible_skills()
        self.assertEqual(sorted(unassigned.mapped('name')), ['chatty', 'demo'])

    def test_a_chat_without_skills_gets_neither_the_block_nor_the_tool(self):
        self.env['muk_ai.skill'].search([]).unlink()
        with self._mock_responses([text_payload()]) as requests:
            self._chat().send_message('hi')
        self.assertNotIn('<available_skills>', self._system_prompt(requests[0]))
        self.assertNotIn('invoke_skill', self._tools(requests[0]))

    def test_the_agent_invokes_a_skill_and_gets_its_body_and_resources(self):
        self._skill(name='on_record', scope='record')
        session = self._chat()
        calls = [
            ('invoke_skill', {'skill_name': 'demo'}, 'c1'),
            ('invoke_skill', {'skill_name': 'on_record'}, 'c2'),
            ('invoke_skill', {'skill_name': 'nope'}, 'c3'),
        ]
        with self._mock_responses([tool_payload(*calls), text_payload('done')]):
            session.send_message('use the demo skill')
        self.assertEqual(
            self._tool_output(session, 'c1'),
            {
                'name': 'demo',
                'label': 'Demo',
                'body': 'Run the demo procedure.',
                'resources': [
                    {
                        'name': 'cheatsheet.md',
                        'uri': f'odoo://attachment/{self.resource.id}',
                        'mimetype': 'text/markdown',
                    }
                ],
            },
        )
        self.assertIn('needs a record open', self._tool_output(session, 'c2')['error'])
        self.assertIn('not available', self._tool_output(session, 'c3')['error'])

    def test_a_slash_command_runs_the_skill_before_the_reply(self):
        for user_input, expected in (('product xy', 'product xy'), ('   ', None)):
            with self.subTest(user_input=user_input):
                session = self._chat()
                with self._mock_responses([text_payload('Acknowledged.')]) as requests:
                    session.invoke_skill_from_chat('demo', user_input=user_input)
                self.assertEqual(
                    (session.state, session.last_text), ('done', 'Acknowledged.')
                )
                kinds = [event['kind'] for event in self._events(session)]
                self.assertEqual(kinds[:2], ['tool_call', 'tool_result'])
                self.assertEqual('user_message' in kinds, bool(expected))
                inputs = requests[0]['inputs']
                call = next(
                    item for item in inputs if item.get('type') == 'function_call'
                )
                self.assertEqual(
                    json.loads(call['arguments']).get('user_input'), expected
                )
                output = self._tool_output(session, call['call_id'])
                self.assertEqual(output['body'], 'Run the demo procedure.')
                if expected:
                    self.assertEqual(inputs[-1]['content'][0]['text'], expected)
                else:
                    self.assertEqual(inputs[-1]['type'], 'function_call_output')

    def test_a_slash_command_is_refused_when_it_cannot_run(self):
        self._skill(name='on_record', scope='record')
        busy = self._chat()
        busy.state = 'running'
        cases = [
            (self._chat(), 'nope', 'not available'),
            (self._chat(), 'on_record', 'needs a record open'),
            (busy, 'demo', 'while the session is running'),
        ]
        for session, name, message in cases:
            with self.subTest(name=name), self.assertRaisesRegex(UserError, message):
                session.invoke_skill_from_chat(name)
        viewer = new_test_user(self.env, login='skill_viewer')
        shared = self._chat()
        shared.share_user_ids = viewer
        with self.assertRaises(AccessError):
            shared.with_user(viewer).invoke_skill_from_chat('demo')

    def test_a_shared_skill_body_is_handed_over_as_text_never_run(self):
        attacker = new_test_user(self.env, login='skill_attacker')
        admin_group = self.env.ref('base.group_system')
        body = (
            "{{ env['res.users'].sudo().browse(%d).write("
            "{'group_ids': [(4, %d)]}) }}" % (attacker.id, admin_group.id)
        )
        self.env['muk_ai.skill'].with_user(attacker).create(
            {
                'name': 'pwn',
                'description': 'x',
                'body': body,
                'user_ids': [Command.clear()],
            }
        )
        session = self._chat()
        with self._mock_responses([text_payload()]):
            snapshot = session.invoke_skill_from_chat('pwn')
        result = next(e for e in snapshot['events'] if e['kind'] == 'tool_result')
        self.assertEqual(result['result']['body'], body)
        self.assertFalse(attacker.has_group('base.group_system'))

    def test_the_snapshot_lists_the_skills_without_their_bodies(self):
        session = self._chat()
        [entry] = session.get_snapshot()['skills']
        self.assertEqual(
            entry,
            {
                'name': 'demo',
                'label': 'Demo',
                'description': 'Do demo things.\nMore detail.',
                'icon': 'flash_on',
                'scope': 'any',
                'models': [],
                'requirement': '',
            },
        )
