from __future__ import annotations

from unittest.mock import patch

from odoo import Command, models
from odoo.exceptions import AccessError
from odoo.tests import new_test_user
from odoo.tools import mute_logger

from odoo.addons.muk_ai.tests.common import AITestCommon, text_payload

USER = {'role': 'user', 'content': [{'type': 'input_text', 'text': 'hi'}]}


class TestSessionQueue(AITestCommon):
    """Verify messages typed while a chat is busy queue up and run as the next turn."""

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _upload(self, session: models.BaseModel, filename: str) -> int:
        """Upload a small text file to the session and return its id."""
        [upload] = session.upload_attachments(
            [{'filename': filename, 'mimetype': 'text/plain', 'data_b64': 'aGk='}]
        )
        return upload['id']

    def _queued(self, snapshot: dict) -> list[str]:
        """Return the contents of the queued messages of a snapshot."""
        return [message['content'] for message in snapshot['pending_user_messages']]

    def _broadcasts(self, sent: list) -> list[list[str]]:
        """Return the queue contents every ``queue`` bus event carried."""
        return [
            [message['content'] for message in payload['payload']['pending']]
            for _target, _type, payload in sent
            if payload.get('type') == 'queue'
        ]

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_only_a_busy_session_queues_messages(self):
        for state in ('running', 'waiting', 'compacting'):
            with self.subTest(state=state):
                session = self._session(state=state)
                upload = self._upload(session, 'one.txt')
                with self._capture_bus() as sent:
                    session.enqueue_message('one', attachment_ids=[upload])
                    snapshot = session.enqueue_message('two')
                self.assertNotIn('queue_rejected_state', snapshot)
                self.assertEqual(
                    [
                        (message['content'], message['attachment_ids'])
                        for message in snapshot['pending_user_messages']
                    ],
                    [('one', [upload]), ('two', [])],
                )
                self.assertEqual(self._broadcasts(sent), [['one'], ['one', 'two']])
                self.assertEqual(session.state, state)
        for state in ('new', 'done', 'stopped', 'error'):
            with self.subTest(state=state):
                session = self._session(state=state)
                with self._capture_bus() as sent:
                    snapshot = session.enqueue_message('too late')
                self.assertEqual(snapshot['queue_rejected_state'], state)
                self.assertEqual(
                    (self._queued(snapshot), self._broadcasts(sent)), ([], [])
                )

    def test_cancel_queued_drops_one_message(self):
        for index, left, broadcasts in (
            (1, ['first', 'third'], [['first', 'third']]),
            (-1, ['first', 'second', 'third'], []),
            (3, ['first', 'second', 'third'], []),
        ):
            with self.subTest(index=index):
                session = self._session(state='running')
                for content in ('first', 'second', 'third'):
                    session.enqueue_message(content)
                with self._capture_bus() as sent:
                    snapshot = session.cancel_queued(index)
                self.assertEqual(self._queued(snapshot), left)
                self.assertEqual(self._broadcasts(sent), broadcasts)

    def test_queued_messages_merge_into_one_turn(self):
        for label, deleted, state, merged in (
            ('every file present', False, 'done', ['first half\n\nsecond half']),
            ('a file was deleted', True, 'error', []),
        ):
            with self.subTest(label):
                session = self._session(state='running', conversation=[USER])
                first = self._upload(session, 'first.txt')
                second = self._upload(session, 'second.txt')
                session.enqueue_message('first half', attachment_ids=[first])
                session.enqueue_message('   ')
                session.enqueue_message('second half', attachment_ids=[second])
                self.env['ir.attachment'].browse(second if deleted else []).unlink()
                self.env.flush_all()
                with self._mock_responses([text_payload('merged')]):
                    self.env['muk_ai.session']._cron_run_pending_sessions()
                self.env.invalidate_all()
                events = self._events(session, 'user_message')
                self.assertEqual(session.state, state)
                self.assertEqual([event['content'] for event in events], merged)
                self.assertEqual(
                    [[file['id'] for file in event['attachments']] for event in events],
                    [[first, second]] * len(merged),
                )
                self.assertEqual(
                    session.pending_ids.mapped('content'),
                    ['first half', '   ', 'second half'] if deleted else [],
                )

    def test_a_message_queued_during_a_turn_runs_next(self):
        session = self._session()
        with self._mock_responses(
            [
                lambda request: (
                    session.enqueue_message('and also this') and text_payload('first')
                ),
                text_payload('second'),
            ]
        ) as requests:
            snapshot = session.send_message('first question')
        self.assertEqual((snapshot['state'], snapshot['last_text']), ('done', 'second'))
        self.assertEqual(
            requests[1]['inputs'][-1]['content'][0]['text'], 'and also this'
        )
        self.assertEqual(
            [event['content'] for event in self._events(session, 'user_message')],
            ['first question', 'and also this'],
        )

    def test_the_event_sequence_moves_past_a_concurrent_writer(self):
        session = self._session()
        session._append_event({'kind': 'note', 'index': 0})
        session._append_event({'kind': 'note', 'index': 1})
        cursor = self.env.cr
        fetchone, stale = cursor.fetchone, []

        def first_read_is_stale() -> tuple:
            """Answer the first read as a writer that cannot see the latest row."""
            row = fetchone()
            if stale:
                return row
            stale.append(row)
            return (0,)

        with (
            patch.object(cursor, 'fetchone', first_read_is_stale),
            mute_logger('odoo.sql_db'),
        ):
            event = session._append_event({'kind': 'note', 'index': 2})
        self.assertEqual(event.sequence, 2)
        self.assertEqual(
            [
                (e.sequence, e.payload['index'])
                for e in session.event_ids.sorted('sequence')
            ],
            [(0, 0), (1, 1), (2, 2)],
        )

    def test_a_reader_never_sees_the_owner_queue(self):
        reader = new_test_user(
            self.env, login='ai_queue_reader', groups='base.group_user'
        )
        session = self._session(
            state='running', share_user_ids=[Command.link(reader.id)]
        )
        session.enqueue_message('just for me')
        self.assertEqual(self._queued(session.get_snapshot()), ['just for me'])
        shared = session.with_user(reader)
        self.assertEqual(self._queued(shared.get_snapshot()), [])
        with self.assertRaises(AccessError):
            shared.enqueue_message('me too')
