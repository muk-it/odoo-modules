from datetime import timedelta

from odoo.exceptions import AccessError, UserError
from odoo.fields import Domain
from odoo.tests import new_test_user

from odoo.addons.muk_ai_subagents.tests.common import (
    SubagentCase,
    text_payload,
    tool_payload,
)


class TestRun(SubagentCase):
    """A lead waits for its subagents, which the user may answer, steer and stop."""

    def test_a_waiting_lead_resumes_once_its_last_subagent_reported(self):
        chat = self._park(2)
        first, second = chat.child_session_ids.sorted('id')
        self.assertEqual(
            (chat.state, chat.pending_ask['kind']), ('waiting', 'children')
        )
        self.assertTrue(chat._public_pending_ask()['queues_input'])
        chat.send_message('And then?')
        self.assertEqual(len(chat.pending_ids), 1)
        with self._mock_responses([text_payload('r0')]):
            first.answer('x')
        self.assertEqual(chat.state, 'waiting')
        with self._mock_responses(
            [text_payload('r1'), text_payload('summary')]
        ) as requests:
            second.answer('y')
        self.assertEqual((chat.state, chat.last_text), ('done', 'summary'))
        self.assertEqual([r['report'] for r in self._reports(chat)], ['r0', 'r1'])
        self.assertEqual(len(self._outputs_for(chat, 'd1')), 1)
        self.assertEqual(requests[1]['inputs'][-1]['content'][0]['text'], 'And then?')
        self.assertFalse(chat.pending_ids)

    def test_stopping_a_run(self):
        for stop in ('action_stop', 'action_stop_subagents'):
            with self.subTest(stop):
                chat = self._park(2)
                with self._mock_responses([text_payload('partial')], repeat_last=True):
                    getattr(chat, stop)()
                children = chat.child_session_ids
                self.assertEqual(set(children.mapped('state')), {'stopped'})
                self.assertEqual(set(children.mapped('stop_reason')), {'stopped'})
                expected = 'stopped' if stop == 'action_stop' else 'done'
                self.assertEqual(chat.state, expected)

    def test_a_subagent_waiting_for_approval_is_announced_through_its_lead(self):
        self._mark_sensitive('res.partner')
        partner = self.env['res.partner'].create({'name': 'Doomed'})
        chat = self._lead_chat()
        delete = tool_payload(
            ('delete_records', {'model': 'res.partner', 'ids': partner.ids}, 'c1')
        )
        with (
            self._capture_bus() as sent,
            self._mock_responses([self._delegate('Delete it'), delete]),
        ):
            chat.start('go')
        child = chat.child_session_ids
        self.assertEqual(child.pending_ask['kind'], 'approval')
        notes = [m for _t, kind, m in sent if kind == 'muk_ai.session_notification']
        self.assertEqual(
            [(n['session_id'], n['message']) for n in notes],
            [(chat.id, 'Worker needs your approval before running a tool')],
        )
        self.assertEqual(
            (chat.notification_unread, child.notification_unread), (True, False)
        )
        with self._mock_responses([text_payload('deleted'), text_payload('synthesis')]):
            child.approve_tool()
        self.assertFalse(partner.exists())
        self.assertEqual((chat.state, chat.last_text), ('done', 'synthesis'))

    def test_a_subagent_never_has_more_rights_than_its_lead(self):
        for lead_mode, worker_mode, expected in [
            ('ask', 'off', 'ask'),
            ('off', 'off', 'off'),
            ('off', 'ask', 'ask'),
        ]:
            with self.subTest(lead=lead_mode, worker=worker_mode):
                self.lead.approval_mode, self.worker.approval_mode = (
                    lead_mode,
                    worker_mode,
                )
                child = self._session(
                    agent_id=self.worker.id, parent_session_id=self._lead_chat().id
                )
                self.assertEqual(child._effective_approval_mode(), expected)
        self.lead.write(
            {'read_only': True, 'tool_filter': ['search_read', 'search_count']}
        )
        child = self._session(
            agent_id=self.worker.id, parent_session_id=self._lead_chat().id
        )
        self.assertEqual(child._enforce_tool_scope(), 'read')
        self.assertEqual(child._available_client_kinds(), set())
        names = {entry['name'] for entry in child._get_filtered_catalog()}
        self.assertEqual(names, {'search_read', 'search_count'})

    def test_a_subagent_ends_with_its_reason_when_a_limit_stops_it(self):
        count = ('search_count', {'model': 'res.partner', 'domain': []})
        requests = {}
        for label, params, rounds, reason in [
            ('rounds', {'muk_ai.max_iterations': 2}, 2, 'max_iterations'),
            ('repeats', {'muk_ai.max_iterations': 20}, 5, 'no_progress'),
            ('budget', {'muk_ai.turn_cost_limit': 1e-9}, 1, 'budget'),
        ]:
            with self.subTest(label):
                self._set_params(params)
                chat = self._lead_chat()
                with self._mock_responses(
                    [
                        self._delegate('Count'),
                        *[tool_payload(count)] * rounds,
                        text_payload('lead'),
                    ]
                ) as requests[label]:
                    chat.start('go')
                child = chat.child_session_ids
                self.assertEqual((child.state, child.stop_reason), ('error', reason))
                self.assertEqual(self._reports(chat)[0]['stop_reason'], reason)
        warned = [
            item['output']
            for item in requests['repeats'][4]['inputs']
            if item.get('type') == 'function_call_output'
        ]
        self.assertIn('<loop_notice>', warned[2])
        self.assertNotIn('<loop_notice>', warned[1])

    def test_a_subagent_has_no_more_time_than_its_parent_has_left(self):
        chat = self._lead_chat()
        child = self._session(agent_id=self.worker.id, parent_session_id=chat.id)
        chat.sudo().turn_wallclock_spent = 3590.0
        self.assertEqual(child._turn_wallclock_seconds(), 30)

    def test_a_run_is_handed_over_whole_and_only_when_idle(self):
        colleague = new_test_user(self.env, 'colleague', groups='base.group_user')
        chat = self._park(1)
        with self.assertRaisesRegex(UserError, 'Stop the subagents'):
            chat.action_handover(colleague.id)
        with self.assertRaisesRegex(UserError, 'handed over with the chat'):
            chat.child_session_ids.action_handover(colleague.id)
        with self._mock_responses([text_payload('stopped')], repeat_last=True):
            chat.action_stop_subagents()
        chat.action_handover(colleague.id)
        self.assertEqual(chat.child_session_ids.user_id, colleague)

    def test_a_reader_of_the_run_sees_its_subagents_but_cannot_steer_them(self):
        reader = new_test_user(self.env, 'reader', groups='base.group_user')
        chat = self._park(1)
        chat.share_user_ids = reader
        child = chat.child_session_ids.with_user(reader)
        roster = chat.with_user(reader).get_snapshot()['subagents']['children']
        self.assertEqual(roster[0]['ask']['text'], 'Q0')
        self.assertEqual(child.get_snapshot()['subagent_of']['parent_id'], chat.id)
        with self.assertRaises(AccessError):
            child.answer('mine')
        stranger = new_test_user(self.env, 'stranger', groups='base.group_user')
        self.assertFalse(child.with_user(stranger).has_access('read'))

    def test_the_roster_says_what_a_working_subagent_does(self):
        chat = self._park(1)
        child = chat.child_session_ids
        self.assertTrue(chat.awaiting_user)
        child.state = 'running'
        self.assertFalse(chat.awaiting_user)
        small = {'model': 'sale.order'}
        large = {'model': 'sale.order', 'note': 'x' * 3000}
        for arguments, shown in [(small, small), (large, {})]:
            with self.subTest(size=len(str(arguments))):
                child._append_event(
                    {
                        'kind': 'tool_call',
                        'name': 'search_read',
                        'arguments': arguments,
                        'call_id': 'x',
                    }
                )
                [entry] = chat._run_payload()['children']
                self.assertEqual(
                    entry['activity'],
                    {'kind': 'tool_call', 'name': 'search_read', 'arguments': shown},
                )
                self.assertFalse(entry['ask'])

    def test_subagents_count_against_no_chat_limit_and_go_with_their_lead(self):
        self.provider.rate_limit = 2
        chat = self._lead_chat()
        with self._mock_responses(
            [
                self._delegate('a', 'b', 'c'),
                *[text_payload('r')] * 3,
                text_payload('ok'),
            ]
        ):
            chat.start('go')
        self.assertEqual(len(chat.child_session_ids), 3)
        self._lead_chat()
        children = chat.child_session_ids
        self._backdate(chat | children, timedelta(days=30))
        swept, _due = self.env['muk_ai.session']._gc_sessions_older_than(1, Domain.TRUE)
        self.assertEqual(swept, 1)
        self.assertFalse(children.exists())
