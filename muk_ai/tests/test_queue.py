from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from unittest.mock import patch

import psycopg2

from odoo import models
from odoo.exceptions import UserError
from odoo.tools import SQL

from odoo.addons.muk_ai.tests.common import AITestCommon
from odoo.addons.muk_ai.tools import ADVISORY_LOCK_NAMESPACE


class TestAiSessionQueue(AITestCommon):
    """Verify the message queue, compaction control, and event sequencing."""

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _busy_session(self, name: str, state: str = 'running') -> models.BaseModel:
        """Create a session already parked in the given busy state."""
        session = self.env['muk_ai.session'].create({'name': name})
        session.write({'state': state})
        return session

    def _upload(self, session: models.BaseModel, filename: str) -> models.BaseModel:
        """Upload a small text attachment on the session and return its record."""
        descriptors = session.upload_attachments(
            [
                {
                    'filename': filename,
                    'mimetype': 'text/plain',
                    'data_b64': 'aGVsbG8=',
                }
            ]
        )
        return self.env['ir.attachment'].browse(descriptors[0]['id'])

    def _bulky_conversation(self, pairs: int, chunk_chars: int) -> list[dict]:
        """Build an alternating user/assistant conversation of a given bulk."""
        filler = 'x' * chunk_chars
        conversation = []
        for index in range(pairs):
            conversation.append(
                {
                    'role': 'user',
                    'content': [{'type': 'input_text', 'text': f'u{index} {filler}'}],
                }
            )
            conversation.append(
                {
                    'type': 'message',
                    'role': 'assistant',
                    'content': [{'type': 'output_text', 'text': f'a{index} {filler}'}],
                }
            )
        return conversation

    def _client_tool_payload(self, name: str, arguments: dict, call_id: str) -> dict:
        """Build a provider payload emitting a single client-executed tool call."""
        return {
            'text': '',
            'tool_calls': [
                {
                    'call_id': call_id,
                    'name': name,
                    'arguments': arguments,
                }
            ],
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

    def _tool_outputs(self, session: models.BaseModel, call_id: str) -> list:
        """Return the conversation tool outputs recorded for a call id."""
        return [
            item
            for item in (session.conversation or [])
            if isinstance(item, dict)
            and item.get('type') == 'function_call_output'
            and item.get('call_id') == call_id
        ]

    def _event_kinds(self, session: models.BaseModel) -> list[str]:
        """Return the kinds of every persisted event of the session."""
        return [e.get('kind') for e in session.fetch_events(limit=500)['events']]

    @contextmanager
    def _as_client_tool(self, *names: str) -> Iterator[None]:
        """Patch the catalog hook so the given tools are client-executed."""
        client_names = set(names)
        with patch.object(
            type(self.env['muk_ai.session']),
            '_client_tool_names',
            autospec=True,
            side_effect=lambda self_arg: client_names,
        ):
            yield

    @contextmanager
    def _capture_bus(self) -> Iterator[list]:
        """Collect the ``(notification_type, message)`` pairs sent on the bus."""
        captured = []
        with patch.object(
            type(self.env['bus.bus']),
            '_sendone',
            autospec=True,
            side_effect=lambda *args, **kwargs: captured.append((args[2], args[3])),
        ):
            yield captured

    @contextmanager
    def _hold_session_lock(self, session_id: int) -> Iterator[None]:
        """Hold the session advisory lock from a separate database connection."""
        cursor = self.env.registry.cursor()
        statement = SQL(
            'SELECT pg_advisory_unlock(%s, %s)',
            ADVISORY_LOCK_NAMESPACE,
            session_id,
        )
        try:
            cursor.execute(
                SQL(
                    'SELECT pg_try_advisory_lock(%s, %s)',
                    ADVISORY_LOCK_NAMESPACE,
                    session_id,
                )
            )
            self.assertTrue(
                cursor.fetchone()[0],
                'failed to acquire the contended session lock',
            )
            yield
        finally:
            with suppress(Exception):
                cursor.execute(statement)
                cursor.fetchone()
            cursor.close()

    # ----------------------------------------------------------
    # Tests: cancel_queued
    # ----------------------------------------------------------

    def test_cancel_queued_removes_only_the_indexed_message(self):
        session = self._busy_session('cancel-middle')
        for text in ('first', 'second', 'third'):
            session.enqueue_message(text)
        snapshot = session.cancel_queued(1)
        self.assertEqual(
            [pending.content for pending in session.pending_ids],
            ['first', 'third'],
        )
        self.assertEqual(
            [entry['content'] for entry in snapshot['pending_user_messages']],
            ['first', 'third'],
        )

    def test_cancel_queued_ignores_out_of_range_indexes(self):
        session = self._busy_session('cancel-out-of-range')
        for text in ('alpha', 'beta'):
            session.enqueue_message(text)
        for index in (-1, 2, 999999):
            snapshot = session.cancel_queued(index)
            self.assertEqual(
                [entry['content'] for entry in snapshot['pending_user_messages']],
                ['alpha', 'beta'],
            )
        self.assertEqual(
            [pending.content for pending in session.pending_ids],
            ['alpha', 'beta'],
        )

    def test_cancel_queued_broadcasts_the_remaining_queue(self):
        session = self._busy_session('cancel-broadcast')
        session.enqueue_message('keep me')
        session.enqueue_message('drop me')
        with self._capture_bus() as captured:
            session.cancel_queued(1)
        queues = [
            message['payload']['pending']
            for _notification_type, message in captured
            if isinstance(message, dict) and message.get('type') == 'queue'
        ]
        self.assertTrue(queues)
        self.assertEqual([entry['content'] for entry in queues[-1]], ['keep me'])

    def test_cancel_queued_out_of_range_broadcasts_nothing(self):
        session = self._busy_session('cancel-silent')
        session.enqueue_message('untouched')
        with self._capture_bus() as captured:
            session.cancel_queued(7)
        self.assertEqual(
            [
                message
                for _notification_type, message in captured
                if isinstance(message, dict) and message.get('type') == 'queue'
            ],
            [],
        )

    # ----------------------------------------------------------
    # Tests: enqueue_message
    # ----------------------------------------------------------

    def test_enqueue_message_queues_while_waiting_or_compacting(self):
        for state in ('waiting', 'compacting'):
            session = self._busy_session(f'queue-{state}', state=state)
            snapshot = session.enqueue_message(f'sent while {state}')
            self.assertNotIn('queue_rejected_state', snapshot)
            self.assertEqual(
                [entry['content'] for entry in snapshot['pending_user_messages']],
                [f'sent while {state}'],
            )
            self.assertEqual(session.state, state)

    def test_enqueue_message_rejects_in_every_terminal_state(self):
        for state in ('new', 'stopped', 'error'):
            session = self._busy_session(f'reject-{state}', state=state)
            snapshot = session.enqueue_message('raced past the turn end')
            self.assertEqual(snapshot['queue_rejected_state'], state)
            self.assertFalse(session.pending_ids)
            self.assertEqual(snapshot['pending_user_messages'], [])

    def test_enqueue_message_payload_carries_attachment_ids(self):
        session = self._busy_session('queue-attachments')
        first = self._upload(session, 'first.txt')
        second = self._upload(session, 'second.txt')
        snapshot = session.enqueue_message(
            'look at these',
            attachment_ids=[first.id, second.id],
        )
        payload = snapshot['pending_user_messages'][0]
        self.assertEqual(payload['id'], session.pending_ids.id)
        self.assertEqual(payload['content'], 'look at these')
        self.assertEqual(payload['attachment_ids'], [first.id, second.id])
        self.assertTrue(payload['queued_at'])
        self.assertEqual(session.pending_ids.attachment_ids, [first.id, second.id])

    def test_enqueue_message_preserves_fifo_order(self):
        session = self._busy_session('queue-fifo')
        for index in range(5):
            session.enqueue_message(f'message-{index}')
        expected = [f'message-{index}' for index in range(5)]
        self.assertEqual([pending.content for pending in session.pending_ids], expected)
        self.assertEqual(
            [
                entry['content']
                for entry in session.get_snapshot()['pending_user_messages']
            ],
            expected,
        )

    # ----------------------------------------------------------
    # Tests: drain
    # ----------------------------------------------------------

    def test_drain_merges_queued_messages_into_one_turn(self):
        session = self._busy_session('drain-merge')
        first = self._upload(session, 'first.txt')
        second = self._upload(session, 'second.txt')
        session.enqueue_message('first half', attachment_ids=[first.id])
        session.enqueue_message('   ')
        session.enqueue_message('second half', attachment_ids=[second.id])
        self.assertTrue(session._drain_pending_message())
        self.assertFalse(session.pending_ids)
        entry = session.conversation[-1]
        self.assertEqual(entry['role'], 'user')
        self.assertEqual(
            [
                block['text']
                for block in entry['content']
                if block['type'] == 'input_text'
            ],
            ['first half\n\nsecond half'],
        )
        self.assertEqual(
            [
                block['attachment_id']
                for block in entry['content']
                if block['type'] == 'muk_ai_attachment'
            ],
            [first.id, second.id],
        )
        self.assertEqual(session.state, 'running')

    def test_drain_logs_one_user_message_event_for_the_merged_turn(self):
        session = self._busy_session('drain-event')
        session.enqueue_message('part one')
        session.enqueue_message('part two')
        session._drain_pending_message()
        events = [
            entry
            for entry in session.fetch_events(limit=500)['events']
            if entry.get('kind') == 'user_message'
        ]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]['content'], 'part one\n\npart two')

    def test_drain_on_empty_queue_is_a_noop(self):
        session = self._busy_session('drain-empty')
        self.assertFalse(session._drain_pending_message())
        self.assertFalse(session.conversation)

    def test_drain_keeps_the_queue_when_a_deleted_attachment_aborts(self):
        session = self._busy_session('drain-deleted-attachment')
        attachment = self._upload(session, 'gone.txt')
        session.enqueue_message('needs the file', attachment_ids=[attachment.id])
        session.enqueue_message('and this one too')
        attachment.unlink()
        try:
            session._drain_pending_message()
        except UserError:
            pass
        else:
            self.fail('_drain_pending_message did not reject the missing file')
        self.assertEqual(
            session.pending_ids.mapped('content'),
            ['needs the file', 'and this one too'],
        )
        self.assertFalse(session.conversation)
        self.assertNotIn('user_message', self._event_kinds(session))

    # ----------------------------------------------------------
    # Tests: stop_compact
    # ----------------------------------------------------------

    def test_stop_compact_cancels_the_streaming_progress_event(self):
        session = self.env['muk_ai.session'].create({'name': 'stop-compacting'})
        event = session._begin_compact_progress(auto=False)
        session.write({'state': 'compacting'})
        snapshot = session.stop_compact()
        self.assertEqual(snapshot['state'], 'done')
        self.assertEqual(session.state, 'done')
        self.assertEqual((event.payload or {}).get('state'), 'cancelled')
        self.assertTrue((event.payload or {}).get('message'))
        self.assertEqual(
            session.fetch_events(limit=500)['events'][-1].get('state'),
            'cancelled',
        )

    def test_stop_compact_keeps_a_finished_progress_event_intact(self):
        session = self.env['muk_ai.session'].create({'name': 'stop-after-summary'})
        event = session._begin_compact_progress(auto=False)
        session._patch_compact_progress(
            event, {'state': 'done', 'summary': 'already written'}
        )
        session.write({'state': 'compacting'})
        session.stop_compact()
        self.assertEqual(session.state, 'done')
        self.assertEqual((event.payload or {}).get('state'), 'done')
        self.assertEqual((event.payload or {}).get('summary'), 'already written')

    def test_stop_compact_is_a_noop_outside_compaction(self):
        for state in ('new', 'running', 'waiting', 'error'):
            session = self._busy_session(f'stop-noop-{state}', state=state)
            before = len(session.event_ids)
            snapshot = session.stop_compact()
            self.assertEqual(snapshot['state'], state)
            self.assertEqual(session.state, state)
            self.assertEqual(len(session.event_ids), before)

    # ----------------------------------------------------------
    # Tests: auto compaction
    # ----------------------------------------------------------

    def test_auto_compact_fires_and_restores_the_running_state(self):
        model = self._create_model('test-auto-compact', context_window=50000)
        agent = self.env['muk_ai.agent'].create(
            {'name': 'Auto compact', 'model_id': model.id}
        )
        session = self.env['muk_ai.session'].create(
            {'name': 'auto-compact', 'agent_id': agent.id}
        )
        session.write(
            {
                'state': 'running',
                'conversation': self._bulky_conversation(5, 20000),
            }
        )
        with self._mock_responses([self._make_text_response('rolling summary')]):
            self.assertTrue(session._maybe_auto_compact())
        self.assertEqual(session.state, 'running')
        self.assertEqual(len(session.conversation), 3)
        self.assertIn(
            'rolling summary',
            session.conversation[0]['content'][0]['text'],
        )
        self.assertEqual(session.conversation[1]['role'], 'user')

    def test_auto_compact_marks_the_progress_event_automatic_and_done(self):
        model = self._create_model('test-auto-compact-event', context_window=50000)
        agent = self.env['muk_ai.agent'].create(
            {'name': 'Auto compact event', 'model_id': model.id}
        )
        session = self.env['muk_ai.session'].create(
            {'name': 'auto-compact-event', 'agent_id': agent.id}
        )
        session.write(
            {
                'state': 'running',
                'conversation': self._bulky_conversation(5, 20000),
            }
        )
        with self._mock_responses([self._make_text_response('condensed history')]):
            session._maybe_auto_compact()
        progress = [
            entry
            for entry in session.fetch_events(limit=500)['events']
            if entry.get('kind') == 'compact_progress'
        ]
        self.assertEqual(len(progress), 1)
        self.assertTrue(progress[0]['auto'])
        self.assertEqual(progress[0]['state'], 'done')
        self.assertEqual(progress[0]['summary'], 'condensed history')

    # ----------------------------------------------------------
    # Tests: event sequences
    # ----------------------------------------------------------

    def test_append_event_allocates_gap_free_sequences(self):
        session = self.env['muk_ai.session'].create({'name': 'sequence-alloc'})
        for index in range(6):
            session._append_event({'kind': 'note', 'index': index})
        events = session.event_ids.sorted('sequence')
        self.assertEqual(events.mapped('sequence'), list(range(6)))
        self.assertEqual(
            [(event.payload or {}).get('index') for event in events],
            list(range(6)),
        )
        self.assertTrue(all((event.payload or {}).get('at') for event in events))

    def test_append_event_sequences_are_scoped_per_session(self):
        first = self.env['muk_ai.session'].create({'name': 'sequence-first'})
        second = self.env['muk_ai.session'].create({'name': 'sequence-second'})
        for index in range(3):
            first._append_event({'kind': 'note', 'index': index})
        for index in range(2):
            second._append_event({'kind': 'note', 'index': index})
        self.assertEqual(
            first.event_ids.sorted('sequence').mapped('sequence'), [0, 1, 2]
        )
        self.assertEqual(second.event_ids.sorted('sequence').mapped('sequence'), [0, 1])

    def test_append_event_retries_after_a_unique_violation(self):
        session = self.env['muk_ai.session'].create({'name': 'sequence-retry'})
        session._append_event({'kind': 'note', 'index': 0})
        event_model = type(self.env['muk_ai.session.event'])
        original_create = event_model.create
        attempts = []

        def flaky(self_arg, vals_list):
            attempts.append(vals_list)
            if len(attempts) == 1:
                msg = 'duplicate key value violates unique constraint'
                raise psycopg2.errors.UniqueViolation(msg)
            return original_create(self_arg, vals_list)

        with patch.object(
            event_model,
            'create',
            autospec=True,
            side_effect=flaky,
        ):
            event = session._append_event({'kind': 'note', 'index': 1})
        self.assertEqual(len(attempts), 2)
        self.assertTrue(event.exists())
        self.assertEqual(event.sequence, 1)
        self.assertEqual(
            session.event_ids.sorted('sequence').mapped('sequence'), [0, 1]
        )

    # ----------------------------------------------------------
    # Tests: client result contention
    # ----------------------------------------------------------

    def test_submit_client_result_rejected_while_the_session_lock_is_held(self):
        session = self.env['muk_ai.session'].create({'name': 'busy-submit'})
        with (
            self._mock_responses(
                [
                    self._client_tool_payload(
                        'browser_click', {'ref': 'e1'}, 'click_1'
                    ),
                    self._make_text_response('clicked it'),
                ]
            ),
            self._as_client_tool('browser_click'),
        ):
            session.start('click the button')
            self.assertEqual(session.state, 'waiting')
            with self._hold_session_lock(session.id):
                with self.assertRaises(UserError):
                    session.submit_client_result('click_1', {'ok': True})
            session.invalidate_recordset()
            self.assertEqual(session.state, 'waiting')
            self.assertEqual((session.pending_ask or {}).get('kind'), 'client_action')
            self.assertFalse((session.pending_ask or {}).get('results'))
            self.assertEqual(self._tool_outputs(session, 'click_1'), [])
            self.assertNotIn('client_action_result', self._event_kinds(session))
            snapshot = session.submit_client_result('click_1', {'ok': True})
        self.assertEqual(snapshot['state'], 'done')
        outputs = self._tool_outputs(session, 'click_1')
        self.assertEqual(len(outputs), 1)
        self.assertEqual(json.loads(outputs[0]['output']), {'ok': True})
        self.assertEqual(self._event_kinds(session).count('client_action_result'), 1)
