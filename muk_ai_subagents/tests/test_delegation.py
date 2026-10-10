from odoo.exceptions import UserError

from odoo.addons.muk_ai.tests.common import text_payload, tool_payload
from odoo.addons.muk_ai_subagents.tests.common import SubagentCase


class TestDelegation(SubagentCase):
    """A lead hands tasks to subagents and receives their reports."""

    def test_a_run_starts_its_subagents_and_hands_their_reports_back_in_order(self):
        chat = self._lead_chat()
        with self._mock_responses(
            [
                self._delegate('First', 'Second'),
                text_payload('one'),
                text_payload('two'),
                text_payload('both'),
            ]
        ) as requests:
            chat.start('go')
        first, second = chat.child_session_ids.sorted('id')
        self.assertEqual((chat.state, chat.last_text), ('done', 'both'))
        self.assertEqual([r['report'] for r in self._reports(chat)], ['one', 'two'])
        self.assertEqual(first.name, 'Worker: First')
        self.assertTrue(first.user_named)
        self.assertEqual((first.stop_reason, second.stop_reason), ('done', 'done'))
        self.assertNotEqual(
            first.delegation_brief['color'], second.delegation_brief['color']
        )
        lead_prompt, child_prompt = (
            self._system_prompt(requests[0]),
            self._system_prompt(requests[1]),
        )
        self.assertIn('- Worker: Looks things up.', lead_prompt)
        self.assertIn(self.lead.delegation_instructions, lead_prompt)
        self.assertIn('<subagent>', child_prompt)
        self.assertNotIn('<subagent>', lead_prompt)
        self.assertEqual(
            requests[1]['inputs'][1]['content'][0]['text'], 'Objective: First'
        )
        self.assertIn('delegate', self._tools(requests[0]))
        self.assertNotIn('delegate', self._tools(requests[1]))
        [start] = self._events(chat, 'delegation_start')
        self.assertEqual([c['id'] for c in start['children']], [first.id, second.id])
        roster = chat.get_snapshot()['subagents']['children']
        self.assertEqual([c['id'] for c in roster], [first.id, second.id])
        self.assertEqual(first.get_snapshot()['subagent_of']['parent_id'], chat.id)

    def test_only_an_agent_allowed_to_delegate_is_offered_the_tool(self):
        quiet = self.lead.copy({'allow_delegation': False})
        for agent, offered in [(self.lead, True), (self.worker, False), (quiet, False)]:
            with self.subTest(agent=agent.name, offered=offered):
                chat = self._session(agent_id=agent.id)
                names = {tool['name'] for tool in chat._get_tool_schema()}
                self.assertEqual('delegate' in names, offered)

    def test_a_delegate_call_is_refused_when_it_cannot_run(self):
        chat = self._park(3)
        idle = self._lead_chat()
        task = {'agent': 'Worker', 'objective': 'More'}
        cases = [
            ('no tasks', idle.id, 'd', [], 'between 1 and'),
            ('not an object', idle.id, 'd', ['x'], 'must be an object'),
            (
                'no objective',
                idle.id,
                'd',
                [{'agent': 'Worker'}],
                'non-empty objective',
            ),
            (
                'not a delegate',
                idle.id,
                'd',
                [{**task, 'agent': 'Lead'}],
                'pick one of',
            ),
            ('through tool_load', idle.id, None, [task], 'directly'),
            ('outside a chat', None, 'd', [task], 'inside an AI session'),
            ('too many at once', chat.id, 'd', [task] * 3, 'At most 5'),
        ]
        for label, session_id, call_id, tasks, message in cases:
            with self.subTest(label), self.assertRaisesRegex(UserError, message):
                self.env['muk_mcp.mixin'].with_context(
                    muk_mcp_session_id=session_id, muk_ai_delegate_call_id=call_id
                )._mcp_delegate(tasks)

    def test_a_refused_delegate_call_is_answered_and_the_lead_goes_on(self):
        chat = self._lead_chat()
        bad = tool_payload(
            ('delegate', {'tasks': [{'agent': 'Nobody', 'objective': 'x'}]}, 'd1')
        )
        with self._mock_responses([bad, text_payload('alone')]):
            chat.start('go')
        self.assertEqual((chat.state, chat.last_text), ('done', 'alone'))
        self.assertFalse(chat.child_session_ids)
        self.assertIn('pick one of', self._tool_output(chat, 'd1')['error'])

    def test_the_rest_of_the_round_runs_once_the_subagents_reported(self):
        chat = self._lead_chat()
        tasks = [{'agent': 'Worker', 'objective': 'Look'}]
        count = {'model': 'res.partner', 'domain': []}
        round_ = tool_payload(
            ('delegate', {'tasks': tasks, 'background': False}, 'd1'),
            ('search_count', count, 's1'),
        )
        with self._mock_responses([round_, self._ask('Which?', 'a1')]):
            chat.start('go')
        self.assertEqual(chat.state, 'waiting')
        self.assertFalse(self._outputs_for(chat, 's1'))
        with self._mock_responses([text_payload('found'), text_payload('done')]):
            chat.child_session_ids.answer('These')
        self.assertEqual((chat.state, chat.last_text), ('done', 'done'))
        self.assertEqual(self._reports(chat)[0]['report'], 'found')
        self.assertIn('count', self._tool_output(chat, 's1'))
