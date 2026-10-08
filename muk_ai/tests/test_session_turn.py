from __future__ import annotations

import re
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from operator import itemgetter, methodcaller
from types import SimpleNamespace
from unittest.mock import patch

from odoo.exceptions import UserError

from odoo.addons.muk_ai.models import session_loop
from odoo.addons.muk_ai.tests.common import AITestCommon, text_payload, tool_payload
from odoo.addons.muk_ai.tools.runtime import MAX_ITERATIONS

USER = {'role': 'user', 'content': [{'type': 'input_text', 'text': 'hi'}]}
REPLY = {
    'type': 'message',
    'role': 'assistant',
    'content': [{'type': 'output_text', 'text': 'hello'}],
}
CALL = {'type': 'function_call', 'name': 'ask_user', 'arguments': '{}', 'call_id': 'q1'}


class TestSessionTurn(AITestCommon):
    """Verify how a chat turn starts, runs its tools, pauses, stops and ends."""

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @contextmanager
    def _clock(self) -> Iterator[Callable[[float], None]]:
        """Run the turn engine on a clock the test moves forward by hand."""
        offset = [0.0]

        def advance(seconds: float) -> None:
            """Move the clock ``seconds`` into the future."""
            offset[0] += seconds

        clock = SimpleNamespace(monotonic=lambda: time.monotonic() + offset[0])
        with patch.object(session_loop, 'time', clock):
            yield advance

    def _rounds_left(self, request: dict) -> int | None:
        """Return the rounds a ``<turn_limits>`` notice of the request announces."""
        for item in request['inputs']:
            for block in item.get('content') or []:
                text = block.get('text') if isinstance(block, dict) else None
                if match := re.search(r'Only (\d+) tool round', text or ''):
                    return int(match.group(1))
        return None

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_a_turn_runs_tools_until_the_model_answers(self):
        partners = {'model': 'res.partner'}
        skipped = 'skipped: terminating tool already ran; emit a short summary and stop'
        for label, payloads, results, executed, outputs, offered in (
            ('one round', [], {}, [], {}, [True]),
            (
                'two rounds',
                [
                    tool_payload(('search_count', partners, 'c1')),
                    tool_payload(('search_read', partners, 'c2')),
                ],
                {'search_count': 5, 'search_read': [{'name': 'ACME'}]},
                ['search_count', 'search_read'],
                {'c1': 5, 'c2': [{'name': 'ACME'}]},
                [True, True, True],
            ),
            (
                'tool error',
                [tool_payload(('search_read', partners, 'c1'))],
                {'search_read': UserError('access denied')},
                ['search_read'],
                {'c1': {'error': 'access denied'}},
                [True, True],
            ),
            (
                'terminating tool',
                [
                    tool_payload(
                        ('open_view', partners, 'c1'), ('search_count', partners, 'c2')
                    )
                ],
                {},
                ['open_view'],
                {'c1': {'ok': True}, 'c2': {'error': skipped}},
                [True, False],
            ),
        ):
            with self.subTest(label):
                session = self._session()
                with (
                    self._patch_tool(results) as calls,
                    self._mock_responses([*payloads, text_payload('done')]) as requests,
                ):
                    snapshot = session.start('help me')
                self.assertEqual(
                    (snapshot['state'], snapshot['last_text']), ('done', 'done')
                )
                self.assertEqual([call['name'] for call in calls], executed)
                self.assertEqual(
                    {
                        call_id: self._tool_output(session, call_id)
                        for call_id in outputs
                    },
                    outputs,
                )
                self.assertEqual(
                    [request['tools_schema'] is not None for request in requests],
                    offered,
                )

    def test_ask_user_pauses_the_turn_until_the_answer(self):
        session = self._session()
        with (
            self._patch_tool() as calls,
            self._mock_responses(
                [
                    tool_payload(
                        ('ask_user', {'question': 'Which year?'}, 'q1'),
                        ('ask_user', {'question': 'Which month?'}, 'q2'),
                        ('search_count', {'model': 'res.partner'}, 'c3'),
                    ),
                    text_payload('Booked for 2026.'),
                ]
            ),
        ):
            snapshot = session.start('Book it')
            self.assertEqual(snapshot['state'], 'waiting')
            self.assertEqual(
                (snapshot['pending_ask']['kind'], snapshot['pending_ask']['text']),
                ('question', 'Which year?'),
            )
            self.assertFalse(snapshot['pending_ask']['queues_input'])
            [upload] = session.upload_attachments(
                [{'filename': 'note.txt', 'mimetype': 'text/plain', 'data_b64': 'aGk='}]
            )
            snapshot = session.answer('2026', attachment_ids=[upload['id']])
        self.assertEqual((snapshot['state'], snapshot['pending_ask']), ('done', None))
        self.assertEqual(calls, [])
        self.assertEqual(
            self._tool_output(session, 'q1'),
            {'status': 'answered', 'question': 'Which year?', 'answer': '2026'},
        )
        self.assertIn(
            'ask_user_already_pending', self._outputs_for(session, 'q2')[0]['output']
        )
        self.assertIn('ask_user pending', self._outputs_for(session, 'c3')[0]['output'])
        [entry] = [item for item in session.conversation if item.get('_answer_entry')]
        self.assertEqual(
            [block['attachment_id'] for block in entry['content']], [upload['id']]
        )
        [event] = self._events(session, 'answer')
        self.assertEqual(
            (event['answer'], [file['id'] for file in event['attachments']]),
            ('2026', [upload['id']]),
        )
        with self.assertRaisesRegex(UserError, 'not waiting for user input'):
            session.answer('2027')

    def test_a_turn_stops_after_the_maximum_rounds(self):
        for configured, rounds in ((3, 3), (0, MAX_ITERATIONS)):
            with self.subTest(configured=configured):
                self._set_params({'muk_ai.max_iterations': configured})
                session = self._session()
                with (
                    self._patch_tool(),
                    self._mock_responses(
                        [tool_payload(('search_count', {}))], repeat_last=True
                    ) as requests,
                ):
                    snapshot = session.start('loop')
                self.assertEqual(
                    (snapshot['state'], snapshot['error_message']),
                    ('error', 'Maximum iterations reached.'),
                )
                self.assertEqual(
                    [self._rounds_left(request) for request in requests],
                    [None] * (rounds - 2) + [2, 1],
                )

    def test_the_turn_wallclock_budget_spans_the_slices(self):
        self._set_params({'muk_ai.turn_wallclock_seconds': 650})
        spent = self._session(
            state='running', conversation=[USER], turn_wallclock_spent=700.0
        )
        self.env.flush_all()
        with self._mock_responses([]) as requests:
            self.env['muk_ai.session']._cron_run_pending_sessions()
        spent.invalidate_recordset()
        self.assertEqual((spent.state, requests), ('error', []))
        for budget, state, error in (
            (3600, 'running', ''),
            (650, 'error', 'Turn wallclock budget reached (650 s).'),
        ):
            with self.subTest(budget=budget):
                self._set_params({'muk_ai.turn_wallclock_seconds': budget})
                session = self._session()
                with (
                    self._clock() as advance,
                    self._patch_tool(),
                    self._mock_responses(
                        [
                            lambda request: (
                                advance(700) or tool_payload(('search_count', {}))
                            )
                        ]
                    ),
                ):
                    session.start('a long job')
                self.assertEqual(session.state, state)
                self.assertIn(error, session.error_message or '')
                self.assertGreaterEqual(session.turn_wallclock_spent, 700)
        with self._mock_responses([text_payload('fresh')]):
            session.send_message('try again')
        self.assertEqual((session.state, session.turn_wallclock_spent), ('done', 0.0))

    def test_a_message_is_routed_by_the_session_state(self):
        question = {'kind': 'question', 'call_id': 'q1', 'text': 'Which?'}
        approval = {'kind': 'approval', 'call_id': 'q1', 'text': 'Sure?'}
        chat, asked = [USER, REPLY], [USER, CALL]
        routes = {
            'start': (1, [], ['user_message'], 2),
            'queue': (0, ['next'], [], 2),
            'answer': (1, [], ['answer'], 4),
            'extend': (1, [], ['user_message'], 4),
        }
        for values, route, state in (
            ({}, 'start', 'done'),
            ({'state': 'running', 'conversation': chat}, 'queue', 'running'),
            ({'state': 'compacting', 'conversation': chat}, 'queue', 'compacting'),
            (
                {'state': 'waiting', 'conversation': asked, 'pending_ask': approval},
                'queue',
                'waiting',
            ),
            (
                {'state': 'waiting', 'conversation': asked, 'pending_ask': question},
                'answer',
                'done',
            ),
            ({'state': 'done', 'conversation': chat}, 'extend', 'done'),
            ({'state': 'stopped', 'conversation': chat}, 'extend', 'done'),
        ):
            with self.subTest(route=route, state=values.get('state')):
                session = self._session(**values)
                with self._mock_responses([text_payload()]) as requests:
                    snapshot = session.send_message('next')
                queued = [item['content'] for item in snapshot['pending_user_messages']]
                logged = [
                    event['kind']
                    for event in self._events(session)
                    if event['kind'] in ('user_message', 'answer')
                ]
                self.assertEqual(
                    (len(requests), queued, logged, len(session.conversation)),
                    routes[route],
                )
                self.assertEqual(snapshot['state'], state)

    def test_the_effort_override_reaches_the_request(self):
        model = self._create_model(
            'test-thinker', reasoning_efforts=['low', 'medium', 'high']
        )
        agent = self.env['muk_ai.agent'].create(
            {'name': 'Thinker', 'model_id': model.id, 'reasoning_effort': 'low'}
        )
        session = self._session(agent_id=agent.id)
        with self._mock_responses([text_payload()], repeat_last=True) as requests:
            session.send_message('agent default')
            snapshot = session.set_reasoning_effort('high')
            session.send_message('override')
            model.reasoning_efforts = ['low', 'medium']
            session.send_message('tier dropped by the model')
        self.assertEqual(
            [request['reasoning_effort'] for request in requests],
            ['low', 'high', 'low'],
        )
        efforts = itemgetter(
            'override_reasoning_effort',
            'effective_reasoning_effort',
            'reasoning_effort_options',
        )
        self.assertEqual(efforts(snapshot), ('high', 'high', ['low', 'medium', 'high']))
        for effort in ('high', 'max'):
            with self.subTest(effort=effort), self.assertRaises(UserError):
                session.set_reasoning_effort(effort)
        snapshot = session.set_reasoning_effort(False)
        self.assertEqual(efforts(snapshot), (False, 'low', ['low', 'medium']))

    def test_the_approval_mode_override_decides_the_gate(self):
        self._mark_sensitive('res.partner')
        delete = tool_payload(
            ('delete_records', {'model': 'res.partner', 'ids': [42]}, 'd1')
        )
        for agent_mode, override, effective, state in (
            ('off', False, 'off', 'done'),
            ('off', 'ask', 'ask', 'waiting'),
            ('ask', 'off', 'off', 'done'),
            ('ask', False, 'ask', 'waiting'),
        ):
            with self.subTest(agent_mode=agent_mode, override=override):
                agent = self.env['muk_ai.agent'].create(
                    {'name': f'Mode {agent_mode}', 'approval_mode': agent_mode}
                )
                session = self._session(agent_id=agent.id)
                snapshot = session.set_approval_mode(override)
                with (
                    self._patch_tool() as calls,
                    self._mock_responses([delete, text_payload('Deleted.')]),
                ):
                    session.send_message('drop partner 42')
                self.assertEqual(snapshot['effective_approval_mode'], effective)
                self.assertEqual(session.state, state)
                self.assertEqual(len(calls), int(state == 'done'))
        with self.assertRaises(UserError):
            session.set_approval_mode('banana')

    def test_the_first_message_names_the_chat(self):
        words = ' '.join(['abcdefghijkl'] * 7)
        for message, name in (
            ('Reset password', 'Reset password'),
            ('  "Refactor\n\n  billing"  ', 'Refactor billing'),
            ('Top 5 customers. Then filter', 'Top 5 customers'),
            ('a b c d e f g h', 'a b c d e f'),
            (words, words[:60]),
            ('   ', 'Test chat'),
        ):
            with self.subTest(message=message):
                session = self._session()
                with self._mock_responses([text_payload()], repeat_last=True):
                    session.send_message(message)
                    session.send_message('Something else entirely')
                self.assertEqual(session.name, name)

    def test_a_cleared_chat_keeps_a_name_the_user_chose(self):
        for chosen, name in ((None, 'Second topic'), ('My budget', 'My budget')):
            with self.subTest(chosen=chosen):
                session = self._session()
                with self._mock_responses([text_payload()], repeat_last=True):
                    session.send_message('First topic')
                    if chosen:
                        session.write({'name': chosen})
                    session.clear()
                    session.send_message('Second topic')
                self.assertEqual(session.name, name)

    def test_a_turn_without_an_answer_ends_in_error(self):
        for answer, error in (
            (text_payload(''), 'AI returned no output.'),
            (UserError('provider down'), 'provider down'),
        ):
            with self.subTest(error=error):
                session = self._session()
                with self._mock_responses([answer]):
                    snapshot = session.start('hello')
                self.assertEqual(
                    (snapshot['state'], snapshot['error_message']), ('error', error)
                )

    def test_a_turn_starts_and_stops_from_a_fitting_state_only(self):
        start, stop = methodcaller('start', 'again'), methodcaller('action_stop')
        for state, call in (
            ('running', start),
            ('waiting', start),
            ('done', methodcaller('answer', 'yes')),
        ):
            with self.subTest(state=state, call=call), self.assertRaises(UserError):
                call(self._session(state=state))
        for state, call, outcome in (
            ('running', stop, 'stopped'),
            ('waiting', stop, 'stopped'),
            ('done', stop, 'done'),
            ('stopped', start, 'done'),
            ('error', start, 'done'),
        ):
            with self.subTest(state=state, call=call):
                session = self._session(state=state)
                with self._mock_responses([text_payload()]):
                    self.assertEqual(call(session)['state'], outcome)
        earlier = {
            'role': 'user',
            'content': [{'type': 'input_text', 'text': 'before'}],
        }
        session = self._session(state='stopped', conversation=[earlier])
        with self._mock_responses([text_payload()]) as requests:
            session.start('again')
        self.assertEqual(
            [item['content'][0]['text'] for item in requests[0]['inputs'][1:3]],
            ['before', 'again'],
        )

    def test_usage_counts_the_turn_and_the_session(self):
        session = self._session()
        with (
            self._patch_tool(),
            self._mock_responses(
                [
                    tool_payload(
                        ('search_count', {}),
                        usage={'input_tokens': 40, 'output_tokens': 2},
                    ),
                    text_payload(usage={'input_tokens': 42, 'output_tokens': 3}),
                    text_payload(usage={'input_tokens': 120, 'output_tokens': 5}),
                ]
            ),
        ):
            first = dict(session.send_message('first')['turn_usage'])
            second = session.send_message('second')
        self.assertEqual(
            [
                (usage['input_tokens'], usage['output_tokens'], usage['iterations'])
                for usage in (first, second['turn_usage'])
            ],
            [(82, 5, 2), (120, 5, 1)],
        )
        self.assertEqual(
            (second['total_input_tokens'], second['total_output_tokens']), (202, 10)
        )
        self.assertEqual(
            (second['last_input_tokens'], second['iteration_count']), (120, 3)
        )
