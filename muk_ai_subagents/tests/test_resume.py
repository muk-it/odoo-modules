from odoo.tests.common import tagged

from .common import SubagentTestCommon


@tagged('post_install', '-at_install', 'muk_ai_subagents')
class TestResume(SubagentTestCommon):
    """Verify parking the parent and resuming it once the last subagent ends."""

    def test_parent_parks_on_live_children(self):
        session = self._park()
        self.assertEqual(session.state, 'waiting')
        pending = session.pending_ask
        self.assertEqual(pending['kind'], 'children')
        self.assertEqual(pending['call_id'], 'd1')
        self.assertEqual(sorted(pending['child_ids']), session.child_session_ids.ids)
        public = session._public_pending_ask()
        self.assertTrue(public['queues_input'])
        self.assertEqual(len(public['children']), 2)
        self.assertTrue(all(child['waiting'] for child in public['children']))
        self.assertNotIn('tool_calls', public)
        self.assertNotIn('outputs', public)
        self.assertEqual(self._delegate_outputs(session), [])

    def test_last_child_resumes_parent_once(self):
        session = self._park()
        first, second = session.child_session_ids.sorted('id')
        with self._mock_responses([self._text('report A')]):
            first.answer('yes')
        self.assertEqual(first.state, 'done')
        self.assertEqual(session.state, 'waiting')
        self.assertEqual(len(self._events(session, 'delegation_result')), 1)
        with self._mock_responses([self._text('report B'), self._text('synthesis')]):
            second.answer('yes')
        self.assertEqual(session.state, 'done')
        self.assertEqual(session.last_text, 'synthesis')
        self.assertFalse(session.pending_ask)
        outputs = self._delegate_outputs(session)
        self.assertEqual(len(outputs), 1)
        self.assertEqual(
            [result['report'] for result in outputs[0]['results']],
            ['report A', 'report B'],
        )
        self.assertEqual(len(self._events(session, 'delegation_result')), 2)
        length = len(session.conversation)
        second._on_child_finished()
        first._on_child_finished()
        self.assertEqual(len(session.conversation), length)
        self.assertEqual(len(self._events(session, 'delegation_result')), 2)

    def test_typing_while_parked_queues(self):
        session = self._park()
        snapshot = session.send_message('hello')
        self.assertEqual(snapshot['state'], 'waiting')
        self.assertEqual(len(snapshot['pending_user_messages']), 1)
        self.assertEqual(session.pending_ask['kind'], 'children')

    def test_parent_stop_stops_children(self):
        session = self._park()
        session.action_stop()
        self.assertEqual(session.state, 'stopped')
        self.assertFalse(session.pending_ask)
        for child in session.child_session_ids:
            self.assertEqual(child.state, 'stopped')
            self.assertEqual(child.stop_reason, 'stopped')

    def test_stopped_child_still_counts_as_finished(self):
        session = self._park()
        first, second = session.child_session_ids.sorted('id')
        with self._mock_responses([self._text('report A')]):
            first.answer('yes')
        with self._mock_responses([self._text('synthesis')]):
            session.subagent_stop(second.id)
        self.assertEqual(second.state, 'stopped')
        self.assertEqual(second.stop_reason, 'stopped')
        self.assertEqual(session.state, 'done')
        results = self._delegate_outputs(session)[0]['results']
        self.assertEqual(results[1]['stop_reason'], 'stopped')
        self.assertEqual(results[0]['report'], 'report A')

    def test_later_calls_in_round_are_skipped_until_resume(self):
        session = self._session()
        payload = self._delegate_payload([self._task('A')])
        payload['tool_calls'].append(
            {
                'call_id': 'c2',
                'name': 'search_read',
                'arguments': {'model': 'res.users'},
            }
        )
        with self._mock_responses([payload, self._ask_payload('Q', 'a0')]):
            session.start('go')
        self.assertEqual(session.state, 'waiting')
        skipped = [
            item
            for item in session.pending_ask['outputs']
            if item.get('call_id') == 'c2'
        ]
        self.assertEqual(len(skipped), 1)
        self.assertIn('delegation pending', skipped[0]['output'])
