from __future__ import annotations

from unittest.mock import patch

from odoo import Command, models
from odoo.exceptions import UserError
from odoo.tests import new_test_user
from odoo.tools import config

from odoo.addons.muk_ai.tests.common import AITestCommon, text_payload, tool_payload


class TestToolLog(AITestCommon):
    """Verify the tool log and the transcript a chat leaves behind."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        """Create the user whose chats call the tools."""
        super().setUpClass()
        cls.user = new_test_user(cls.env, login='log_user')

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _logs(self, session: models.BaseModel) -> models.BaseModel:
        """Return the tool log rows of ``session``."""
        return self.env['muk_mcp.log'].search([('session_id', '=', session.id)])

    def _lookup_turn(self, session: models.BaseModel) -> None:
        """Run a turn on ``session`` that calls one tool and then answers."""
        with (
            self._patch_tool(),
            self._mock_responses(
                [
                    tool_payload(('search_read', {'model': 'res.partner'})),
                    text_payload(),
                ]
            ),
        ):
            session.send_message('Find the partners')

    def _seed(self, session: models.BaseModel, count: int, **values) -> None:
        """Append ``count`` numbered text lines to the transcript of ``session``."""
        self.env['muk_ai.session.event'].create(
            [
                {
                    'session_id': session.id,
                    'sequence': index,
                    'kind': 'text',
                    'payload': {'kind': 'text', 'content': f'msg-{index}'},
                    **values,
                }
                for index in range(count)
            ]
        )

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_a_chat_logs_every_tool_call_it_makes(self):
        session = (
            self.env['muk_ai.session'].with_user(self.user).create({'name': 'Log'})
        )
        with (
            self._patch_tool({'read_records': UserError('no such record')}),
            self._mock_responses(
                [
                    tool_payload(
                        ('search_read', {'model': 'res.partner'}),
                        ('read_records', {'model': 'res.company', 'ids': [0]}),
                    ),
                    tool_payload(
                        ('ask_user', {'question': 'Which one?'}),
                        ('search_read', {'model': 'res.users'}),
                    ),
                ]
            ),
        ):
            session.send_message('Find the partners')
            self.env['muk_mcp.tool']._call(
                'search_read', {'model': 'res.country'}, self.env
            )
        self.assertEqual(session.state, 'waiting')
        rows = self._logs(session)
        self.assertEqual(
            sorted((row.model_name, row.status) for row in rows),
            [('res.company', 'error'), ('res.partner', 'ok'), ('res.users', 'denied')],
        )
        self.assertEqual(rows.user_id, self.user)
        self.assertEqual(set(rows.mapped('source')), {'chat'})
        outside = self.env['muk_mcp.log'].search([('model_name', '=', 'res.country')])
        self.assertEqual(outside.mapped('source'), ['mcp'])
        self.assertFalse(outside.session_id)

    def test_the_audit_switch_decides_whether_chat_calls_are_logged(self):
        refused = tool_payload(
            ('ask_user', {'question': 'Which one?'}),
            ('search_read', {'model': 'res.users'}),
        )
        for logging, logged in ((True, ['denied', 'ok']), (False, [])):
            with (
                self.subTest(logging=logging),
                patch.dict(config.options, {'mcp_logging': logging}),
                self._patch_tool(),
                self._mock_responses(
                    [tool_payload(('search_read', {'model': 'res.partner'})), refused]
                ),
            ):
                session = self._session()
                session.send_message('Find the partners')
                self.assertEqual(sorted(self._logs(session).mapped('status')), logged)
                self.assertEqual(
                    [
                        event['kind']
                        for event in self._events(session)
                        if event['kind'].startswith('tool_')
                    ],
                    ['tool_call', 'tool_result'] * 2,
                )

    def test_the_log_lives_as_long_as_its_chat(self):
        session = self._session()
        self._lookup_turn(session)
        rows = self._logs(session)
        self.assertEqual(len(rows), 1)
        session.clear()
        self.assertEqual(self._logs(session), rows)
        session.unlink()
        self.assertFalse(rows.exists())

    def test_fetch_events_pages_back_through_the_transcript(self):
        session = self._session()
        self._seed(session, 250)
        for label, kwargs, first, last, more in (
            ('latest window', {'limit': 100}, 150, 249, True),
            ('older page', {'limit': 100, 'before_sequence': 150}, 50, 149, True),
            ('oldest page', {'limit': 100, 'before_sequence': 50}, 0, 49, False),
            ('everything', {'limit': 300}, 0, 249, False),
        ):
            with self.subTest(label):
                window = session.fetch_events(**kwargs)
                self.assertEqual(
                    [event['content'] for event in window['events']],
                    [f'msg-{index}' for index in range(first, last + 1)],
                )
                self.assertEqual(window['has_more_older'], more)
                self.assertEqual(window['oldest_sequence'], first)

    def test_a_private_line_reaches_only_the_person_it_is_about(self):
        reader = new_test_user(self.env, login='log_reader')
        heir = new_test_user(self.env, login='log_heir')
        session = self.env['muk_ai.session'].with_user(self.user).create({'name': 'Me'})
        session.sudo().share_user_ids = [Command.set(reader.ids)]
        self._seed(session, 1)
        with self._capture_bus() as sent:
            note = session._append_event(
                {'kind': 'note', 'content': 'about me', 'private_user_id': self.user.id}
            )
        self.assertEqual([target for target, _type, _message in sent], [self.user])
        fork = session.browse(session.with_user(self.user).fork_at_event(note.id))
        handed = session.browse(session.with_user(self.user).fork_at_event(note.id))
        handed.with_user(self.user).action_handover(heir.id)
        for label, chat, user, kinds in (
            ('the person it is about', session, self.user, ['text', 'note']),
            ('a reader', session, reader, ['text']),
            ('the fork of that person', fork, self.user, ['text', 'note']),
            ('the next owner of a fork', handed, heir, ['text']),
        ):
            with self.subTest(label):
                window = chat.with_user(user).fetch_events(limit=1)
                self.assertEqual(window['events'][0]['kind'], kinds[-1])
                self.assertEqual(window['has_more_older'], len(kinds) > 1)
                events = chat.with_user(user).fetch_events()['events']
                self.assertEqual([event['kind'] for event in events], kinds)
