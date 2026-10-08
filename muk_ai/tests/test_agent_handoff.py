from __future__ import annotations

import json

from odoo import models
from odoo.exceptions import UserError

from odoo.addons.muk_ai.tests.common import AITestCommon, text_payload, tool_payload


class TestAgentHandoff(AITestCommon):
    """Verify the coordinator hands a chat to a specialist through the handoff tools."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        """Create a coordinator, a specialist and two agents that take no handoff."""
        super().setUpClass()
        agents = cls.env['muk_ai.agent']
        cls.coordinator = agents.create(
            {
                'name': 'Test Coordinator',
                'system_prompt': 'You are the coordinator.',
                'allow_handoff': True,
                'tool_filter': ['list_agents', 'switch_agent', 'search_read'],
                'essential_tool_names': ['list_agents', 'switch_agent'],
            }
        )
        cls.specialist = agents.create(
            {
                'name': 'Test Specialist',
                'system_prompt': 'You are the specialist.',
                'allow_handoff': True,
                'tool_filter': ['read_records', 'switch_agent'],
                'essential_tool_names': ['read_records'],
            }
        )
        cls.private = agents.create({'name': 'Test Private', 'allow_handoff': False})
        cls.retired = agents.create(
            {'name': 'Test Retired', 'allow_handoff': True, 'active': False}
        )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _call(self, session: models.BaseModel, name: str, arguments: dict) -> object:
        """Run a handoff tool bound to ``session``, as a chat dispatches it."""
        env = self.env(context={**self.env.context, 'muk_mcp_session_id': session.id})
        text, _info = env['muk_mcp.tool']._call(name, arguments, env)
        return json.loads(text)

    def _markers(self, session: models.BaseModel) -> list[tuple[str, str]]:
        """Return the ``(from, to)`` agent names of every switch marker."""
        return [
            (event['from_agent_name'], event['agent_name'])
            for event in self._events(session, 'agent_switched')
        ]

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_the_coordinator_hands_the_turn_to_the_specialist(self):
        session = self._session(agent_id=self.coordinator.id)
        session.expanded_tool_names = ['search_read']
        with self._mock_responses(
            [
                tool_payload(
                    ('list_agents', {}, 'c1'),
                    ('switch_agent', {'agent': self.specialist.id}, 'c2'),
                ),
                text_payload('done'),
            ]
        ) as requests:
            session.send_message('route me')
        listed = self._tool_output(session, 'c1')
        names = {agent['name'] for agent in listed}
        self.assertIn('Test Specialist', names)
        self.assertFalse(names & {'Test Coordinator', 'Test Private', 'Test Retired'})
        self.assertEqual(session.agent_id, self.specialist)
        self.assertEqual(session.state, 'done')
        self.assertFalse(session.expanded_tool_names)
        system = self._system_prompt(requests[1])
        self.assertIn('You are the specialist.', system)
        self.assertNotIn('You are the coordinator.', system)
        tools = self._tools(requests[1])
        self.assertIn('read_records', tools)
        self.assertNotIn('list_agents', tools)
        self.assertEqual(
            self._markers(session), [('Test Coordinator', 'Test Specialist')]
        )

    def test_only_an_active_handoff_agent_can_take_over(self):
        for agent, taker in (
            (self.specialist.id, self.specialist),
            ('Test Specialist', self.specialist),
            (self.private.id, self.coordinator),
            (self.retired.id, self.coordinator),
            ('Nobody', self.coordinator),
        ):
            with self.subTest(agent=agent):
                session = self._session(agent_id=self.coordinator.id)
                if taker == self.coordinator:
                    with self.assertRaisesRegex(UserError, 'No handoff-enabled agent'):
                        self._call(session, 'switch_agent', {'agent': agent})
                else:
                    self._call(session, 'switch_agent', {'agent': agent})
                self.assertEqual(session.agent_id, taker)

    def test_a_switch_marker_is_left_only_when_the_agent_changes(self):
        switch = {'agent_id': self.specialist.id}
        for transcript, values, markers in (
            (True, switch, [('Test Coordinator', 'Test Specialist')]),
            (True, {'agent_id': self.coordinator.id}, []),
            (True, {'name': 'renamed'}, []),
            (False, switch, []),
        ):
            with self.subTest(transcript=transcript, values=values):
                session = self._session(agent_id=self.coordinator.id)
                if transcript:
                    session._append_event({'kind': 'user_message', 'content': 'hi'})
                with self._capture_bus() as sent:
                    session.write(values)
                self.assertEqual(self._markers(session), markers)
                self.assertEqual(
                    any(
                        message.get('type') == 'agent_switched'
                        for _target, _kind, message in sent
                    ),
                    values is switch,
                )
