from __future__ import annotations

import json

from odoo import models
from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.muk_ai.tests.common import AITestCommon


@tagged('post_install', '-at_install', 'muk_ai')
class TestAgentHandoff(AITestCommon):
    """Verify the switch_agent / list_agents handoff tools."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        agents = cls.env['muk_ai.agent']
        cls.router = agents.create(
            {
                'name': 'Test Router',
                'system_prompt': 'You are the router.',
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
        cls.private_agent = agents.create(
            {
                'name': 'Test Private',
                'system_prompt': 'Not a target.',
                'allow_handoff': False,
            }
        )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _session(self, agent: models.Model) -> models.Model:
        """Return a fresh session owned by the current user for the agent."""
        return self.env['muk_ai.session'].create(
            {'name': 'handoff', 'agent_id': agent.id}
        )

    def _mixin(self, session: models.Model) -> models.Model:
        """Return the MCP mixin bound to the given session context."""
        return self.env['muk_mcp.mixin'].with_context(muk_mcp_session_id=session.id)

    def _tool_payload(self, name: str, arguments: dict, call_id: str) -> dict:
        """Build a provider payload emitting a single tool call."""
        return {
            'text': '',
            'tool_calls': [{'call_id': call_id, 'name': name, 'arguments': arguments}],
            'carry_inputs': [
                {
                    'type': 'function_call',
                    'name': name,
                    'arguments': json.dumps(arguments),
                    'call_id': call_id,
                }
            ],
            'usage': {'input_tokens': 4, 'output_tokens': 2},
        }

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_switch_agent_changes_agent_and_clears_expanded(self):
        session = self._session(self.router)
        session.expanded_tool_names = ['read_records']
        result = self._mixin(session)._mcp_switch_agent(self.specialist.id)
        self.assertEqual(result['agent_id'], self.specialist.id)
        self.assertEqual(session.agent_id, self.specialist)
        self.assertFalse(session.expanded_tool_names)

    def test_switch_agent_updates_system_prompt_and_tools(self):
        session = self._session(self.router)
        before = session._build_request_inputs()[0]['content'][0]['text']
        self.assertIn('You are the router.', before)
        session._dispatch_tool_call('switch_agent', {'agent': self.specialist.id}, 'c1')
        after = session._build_request_inputs()[0]['content'][0]['text']
        self.assertIn('You are the specialist.', after)
        self.assertNotIn('You are the router.', after)
        schema_names = {entry['name'] for entry in session._get_tool_schema()}
        self.assertIn('read_records', schema_names)

    def test_switch_agent_by_name(self):
        session = self._session(self.router)
        self._mixin(session)._mcp_switch_agent('Test Specialist')
        self.assertEqual(session.agent_id, self.specialist)

    def test_list_agents_returns_only_handoff_targets(self):
        session = self._session(self.router)
        names = {agent['name'] for agent in self._mixin(session)._mcp_list_agents()}
        self.assertIn('Test Specialist', names)
        self.assertNotIn('Test Router', names)
        self.assertNotIn('Test Private', names)

    def test_switch_agent_rejects_non_handoff(self):
        session = self._session(self.router)
        with self.assertRaises(UserError):
            self._mixin(session)._mcp_switch_agent(self.private_agent.id)

    def test_switch_agent_rejects_inactive(self):
        session = self._session(self.router)
        self.specialist.active = False
        with self.assertRaises(UserError):
            self._mixin(session)._mcp_switch_agent(self.specialist.id)

    def test_switch_agent_is_not_terminating(self):
        session = self._session(self.router)
        self.assertNotIn('switch_agent', session._get_terminating_tools())

    def test_switch_agent_continues_loop_as_new_agent(self):
        session = self._session(self.router)
        with self._mock_responses(
            [
                self._tool_payload('switch_agent', {'agent': self.specialist.id}, 'c1'),
                self._make_text_response('done'),
            ]
        ):
            session.start('route me')
        self.assertEqual(session.agent_id, self.specialist)
        self.assertEqual(session.state, 'done')

    # ----------------------------------------------------------
    # Agent-switch transcript marker (write() chokepoint)
    # ----------------------------------------------------------

    def _switch_events(self, session: models.Model) -> models.Model:
        """Return the persisted ``agent_switched`` events for the session."""
        return self.env['muk_ai.session.event'].search(
            [('session_id', '=', session.id), ('kind', '=', 'agent_switched')]
        )

    def test_write_agent_change_persists_one_marker(self):
        session = self._session(self.router)
        session.write({'agent_id': self.specialist.id})
        events = self._switch_events(session)
        self.assertEqual(len(events), 1)
        self.assertEqual(events.payload.get('agent_name'), 'Test Specialist')
        self.assertEqual(events.payload.get('from_agent_name'), 'Test Router')

    def test_create_with_agent_persists_no_marker(self):
        session = self._session(self.specialist)
        self.assertFalse(self._switch_events(session))

    def test_write_same_agent_persists_no_marker(self):
        session = self._session(self.router)
        session.write({'agent_id': self.router.id})
        self.assertFalse(self._switch_events(session))

    def test_write_without_agent_id_persists_no_marker(self):
        session = self._session(self.router)
        session.write({'name': 'renamed'})
        self.assertFalse(self._switch_events(session))

    def test_mcp_switch_agent_persists_one_marker(self):
        session = self._session(self.router)
        self._mixin(session)._mcp_switch_agent(self.specialist.id)
        events = self._switch_events(session)
        self.assertEqual(len(events), 1)
        self.assertEqual(events.payload.get('agent_name'), 'Test Specialist')
