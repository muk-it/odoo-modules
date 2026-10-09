from __future__ import annotations

import json
from operator import methodcaller

from odoo import models
from odoo.exceptions import UserError

from odoo.addons.muk_ai.tests.common import (
    AITestCommon,
    PNG_1x1,
    text_payload,
    tool_payload,
)
from odoo.addons.muk_mcp.tools.protocol import (
    ToolResult,
    make_media_content,
    make_text_content,
    make_tool_result,
)


class TestSessionHistory(AITestCommon):
    """Verify clearing, compacting, regenerating, rewinding and forking a chat."""

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _bulky(self, pairs: int, size: int) -> list[dict]:
        """Build ``pairs`` user and assistant messages of ``size`` characters each."""
        filler = 'x' * size
        return [
            item
            for index in range(pairs)
            for item in (
                {
                    'role': 'user',
                    'content': [{'type': 'input_text', 'text': f'{filler} u{index}'}],
                },
                {
                    'type': 'message',
                    'role': 'assistant',
                    'content': [{'type': 'output_text', 'text': f'{filler} a{index}'}],
                },
            )
        ]

    def _shape(self, conversation: list) -> list[str]:
        """Name each conversation item by the last word of its text, or its type."""
        return [
            (
                ' '.join(
                    block.get('text', '') for block in item.get('content') or []
                ).split()[-1:]
                or [item.get('type')]
            )[0]
            for item in conversation or []
        ]

    def _play(self, session: models.BaseModel, step: str) -> None:
        """Advance the chat by one step: a question, a command, a file or an image."""
        if step == 'clear':
            session.clear()
            return
        payloads, results = [text_payload(step.replace('q', 'a'))], {}
        if step == 'compact':
            payloads = [text_payload('summary')]
        elif step == 'asks':
            payloads = [
                tool_payload(('ask_user', {'question': 'Which?'}, 'q')),
                text_payload('filed'),
            ]
        elif step == 'looks':
            image = make_tool_result(
                [make_text_content('a chart'), make_media_content(PNG_1x1, 'image/png')]
            )
            payloads = [tool_payload(('search_read', {}, 'c1')), text_payload('seen')]
            results = {'search_read': ToolResult(image)}
        with self._patch_tool(results), self._mock_responses(payloads):
            if step == 'compact':
                session.compact()
            else:
                session.send_message(step)
            if step == 'asks':
                [upload] = session.upload_attachments(
                    [
                        {
                            'filename': 'a.txt',
                            'mimetype': 'text/plain',
                            'data_b64': 'aGk=',
                        }
                    ]
                )
                session.answer('this one', attachment_ids=[upload['id']])

    def _event_id(self, session: models.BaseModel, kind: str, content: str) -> int:
        """Return the id of the session event of ``kind`` carrying ``content``."""
        return next(
            event['event_id']
            for event in self._events(session, kind)
            if event['content'] == content
        )

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_clear_starts_over_and_keeps_the_log(self):
        session = self._session()
        self._play(session, 'q1')
        self.env['muk_ai.session.pending'].create(
            {'session_id': session.id, 'content': 'later'}
        )
        session.approved_signatures = ['delete_records:res.partner']
        before = self._events(session)
        snapshot = session.clear()
        self.assertEqual(
            (
                snapshot['state'],
                snapshot['iteration_count'],
                snapshot['last_input_tokens'],
            ),
            ('new', 0, 0),
        )
        self.assertEqual(
            (snapshot['turn_usage'], snapshot['pending_user_messages']), ({}, [])
        )
        self.assertFalse(session.conversation or session.approved_signatures)
        self.assertTrue(session.cleared_at)
        after = self._events(session)
        self.assertEqual(after[: len(before)], before)
        self.assertEqual(
            [(e['kind'], e['name']) for e in after[len(before) :]],
            [('command', '/clear')],
        )

    def test_compact_summarizes_the_head_and_keeps_the_tail(self):
        session = self._session(
            state='done', conversation=self._bulky(10, 10000), last_input_tokens=50000
        )
        tail = session.conversation[-2:]
        with self._mock_responses(
            [
                text_payload(
                    'first summary', usage={'input_tokens': 1234, 'output_tokens': 56}
                )
            ]
        ) as requests:
            snapshot = session.compact()
        self.assertIsNone(requests[0]['tools_schema'])
        self.assertEqual(
            (snapshot['state'], snapshot['last_input_tokens']), ('done', 0)
        )
        self.assertEqual(session.total_input_tokens, 1234)
        summary, *kept = session.conversation
        self.assertEqual(summary['role'], 'assistant')
        self.assertIn('first summary', summary['content'][0]['text'])
        self.assertEqual((kept[0]['role'], kept[-2:]), ('user', tail))
        self.assertLess(len(kept), 20)
        progress = self._events(session, 'compact_progress')[-1]
        self.assertEqual(
            (
                progress['state'],
                progress['auto'],
                progress['summary'],
                progress['original_tokens'],
            ),
            ('done', False, 'first summary', 50000),
        )
        session.conversation = [*session.conversation, *self._bulky(10, 10000)]
        with self._mock_responses([text_payload('second summary')]) as requests:
            session.compact()
        system, *_conversation, closing = requests[0]['inputs']
        self.assertIn(
            '<previous-summary>\nfirst summary\n</previous-summary>',
            system['content'][0]['text'],
        )
        self.assertNotIn('## Goal', closing['content'][0]['text'])

    def test_a_compaction_that_fails_leaves_a_usable_chat(self):
        for label, answer, short, fallback, notice in (
            (
                'provider fails',
                RuntimeError('context_length_exceeded'),
                False,
                'tail_drop',
                'dropped',
            ),
            ('empty summary', text_payload(''), False, None, 'no summary'),
            (
                'stopped by the user',
                lambda request: session.stop_compact() and text_payload('late'),
                False,
                None,
                'cancelled by user',
            ),
            ('nothing to compact', None, True, None, 'too short'),
        ):
            with self.subTest(label):
                conversation = self._bulky(1 if short else 8, 8000)
                session = self._session(state='done', conversation=conversation)
                with self._mock_responses([answer] if answer else []) as requests:
                    snapshot = session.compact()
                progress = self._events(session, 'compact_progress')[-1]
                self.assertEqual(
                    (snapshot['state'], len(requests)), ('done', int(not short))
                )
                self.assertEqual(progress.get('fallback'), fallback)
                self.assertIn(
                    notice, progress.get('summary') or progress.get('message')
                )
                self.assertEqual(session.conversation == conversation, not fallback)

    def test_stop_compact_only_cancels_a_running_compaction(self):
        session = self._session(state='done', conversation=self._bulky(8, 8000))
        self._play(session, 'compact')
        session.write({'state': 'compacting'})
        self.assertEqual(session.stop_compact()['state'], 'done')
        self.assertEqual(
            self._events(session, 'compact_progress')[-1]['summary'], 'summary'
        )
        for state in ('new', 'running', 'waiting', 'error'):
            with self.subTest(state=state):
                session = self._session(state=state)
                self.assertEqual(session.stop_compact()['state'], state)
                self.assertEqual(self._events(session), [])

    def test_auto_compact_runs_when_the_request_nears_the_window(self):
        model = self._create_model('test-small-window', context_window=50000)
        agent = self.env['muk_ai.agent'].create(
            {'name': 'Small window', 'model_id': model.id}
        )
        short = [
            {'role': 'user', 'content': [{'type': 'input_text', 'text': 'hi'}]},
            {
                'type': 'message',
                'role': 'assistant',
                'content': [{'type': 'output_text', 'text': 'hello'}],
            },
        ]
        for label, conversation, message, summarized in (
            ('the history fills the window', self._bulky(5, 20000), 'next', True),
            ('the new message alone fills it', short, 'x' * 250000, False),
        ):
            with self.subTest(label):
                session = self._session(
                    agent_id=agent.id, state='done', conversation=conversation
                )
                payloads = [text_payload('rolling summary')] * summarized + [
                    text_payload('answer')
                ]
                with self._mock_responses(payloads) as requests:
                    session.send_message(message)
                progress = self._events(session, 'compact_progress')
                self.assertEqual(session.state, 'done')
                self.assertEqual(
                    [request['tools_schema'] is None for request in requests],
                    [True, False][not summarized :],
                )
                self.assertEqual(
                    [(event['auto'], event['state']) for event in progress],
                    [(True, 'done')] * summarized,
                )
                self.assertEqual(
                    'rolling summary' in json.dumps(session.conversation), summarized
                )

    def test_regenerate_replays_the_last_question(self):
        session = self._session()
        self._play(session, 'q1')
        with self._mock_responses([text_payload('again')]) as requests:
            snapshot = session.regenerate_last_turn()
        self.assertEqual(snapshot['last_text'], 'again')
        self.assertEqual(self._shape(session.conversation), ['q1', 'again'])
        self.assertEqual(self._shape(requests[0]['inputs'][1:]), ['q1'])
        self.assertEqual(
            [
                (e['kind'], e['content'])
                for e in self._events(session)
                if e['kind'] in ('user_message', 'text')
            ],
            [('user_message', 'q1'), ('text', 'again')],
        )

    def test_undo_and_fork_cut_at_every_boundary(self):
        for steps, kind, content, shape, state in (
            (('q1', 'q2', 'q3'), 'user_message', 'q2', ['q1', 'a1'], 'done'),
            (('q1', 'q2', 'q3'), 'text', 'a2', ['q1', 'a1', 'q2'], 'done'),
            (('q1', 'clear', 'q2'), 'user_message', 'q2', [], 'new'),
            (
                ('q1', 'q2', 'compact', 'q3'),
                'user_message',
                'q3',
                ['summary', 'q2', 'a2'],
                'done',
            ),
            (('q1', 'asks', 'q2'), 'user_message', 'asks', ['q1', 'a1'], 'done'),
            (('q1', 'looks', 'q2'), 'user_message', 'looks', ['q1', 'a1'], 'done'),
        ):
            with self.subTest(undo=steps, at=content):
                session = self._session()
                for step in steps:
                    self._play(session, step)
                target = self._event_id(session, kind, content)
                snapshot = session.undo_to_event(target)
                self.assertNotIn(
                    target, [event['event_id'] for event in snapshot['events']]
                )
                self.assertEqual(self._shape(session.conversation), shape)
                self.assertEqual(snapshot['state'], state)
        for steps, shape in (
            (('q1', 'q2', 'q3'), ['q1', 'a1', 'q2']),
            (('q1', 'clear', 'q2', 'q3'), ['q2']),
        ):
            with self.subTest(fork=steps):
                session = self._session()
                for step in steps:
                    self._play(session, step)
                before = list(session.conversation)
                fork = self.env['muk_ai.session'].browse(
                    session.fork_at_event(self._event_id(session, 'user_message', 'q2'))
                )
                self.assertEqual(session.conversation, before)
                self.assertEqual(self._shape(fork.conversation), shape)
                self.assertEqual(self._events(fork)[-1]['content'], 'q2')
                self.assertEqual(
                    (fork.name, fork.state, fork.agent_id),
                    (f'{session.name} (fork)', 'done', session.agent_id),
                )

    def test_history_cannot_be_rewritten_while_busy(self):
        session = self._session()
        self._play(session, 'q1')
        event = self._events(session)[0]['event_id']
        calls = {
            'regenerate': methodcaller('regenerate_last_turn'),
            'undo': methodcaller('undo_to_event', event),
            'fork': methodcaller('fork_at_event', event),
            'clear': methodcaller('clear'),
            'compact': methodcaller('compact'),
        }
        for record, state, refused in (
            (session, 'running', ('regenerate', 'undo', 'fork', 'clear', 'compact')),
            (session, 'compacting', ('regenerate', 'undo', 'fork', 'clear', 'compact')),
            (session, 'waiting', ('regenerate', 'undo', 'compact')),
            (self._session(), 'new', ('regenerate', 'compact')),
        ):
            record.write({'state': state})
            for name in refused:
                with self.subTest(state=state, call=name), self.assertRaises(UserError):
                    calls[name](record)

    def test_unanswered_tool_calls_are_closed(self):
        self._mark_sensitive('res.partner')
        session = self._session()
        with self._mock_responses(
            [
                tool_payload(
                    ('delete_records', {'model': 'res.partner', 'ids': [42]}, 'd1'),
                    ('search_count', {'model': 'res.partner'}, 'c2'),
                )
            ]
        ):
            session.send_message('drop partner 42')
        self.assertEqual(session.action_stop()['state'], 'stopped')
        session.conversation = [
            *session.conversation,
            {
                'type': 'function_call',
                'name': 'search_count',
                'arguments': '{}',
                'call_id': 'c3',
            },
        ]
        with self._mock_responses([text_payload()], repeat_last=True):
            session.send_message('next')
            session.send_message('again')
        self.assertEqual(
            {
                call_id: [
                    json.loads(item['output'])
                    for item in self._outputs_for(session, call_id)
                ]
                for call_id in ('d1', 'c2', 'c3')
            },
            {
                'd1': [{'status': 'cancelled', 'reason': 'stopped_by_user'}],
                'c2': [{'status': 'cancelled', 'reason': 'stopped_by_user'}],
                'c3': [{'error': 'interrupted', 'reason': 'tool result missing'}],
            },
        )
        asked = self._session()
        with self._mock_responses(
            [tool_payload(('ask_user', {'question': 'Who?'}, 'q1'))]
        ):
            asked.send_message('ask me')
        asked.action_stop()
        self.assertEqual(
            [json.loads(item['output']) for item in self._outputs_for(asked, 'q1')],
            [{'status': 'cancelled', 'reason': 'stopped_by_user'}],
        )
