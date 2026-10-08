from __future__ import annotations

from collections.abc import Callable
from unittest.mock import MagicMock, patch

from odoo import Command, models
from odoo.exceptions import UserError
from odoo.tests import new_test_user

from odoo.addons.muk_ai.tests.common import AITestCommon, text_payload, tool_payload


class TestSessionBus(AITestCommon):
    """Verify which users and channels each kind of chat notification reaches."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        """Create the owner, the reader, a stranger and their shared chat."""
        super().setUpClass()
        cls.owner = new_test_user(cls.env, login='bus_owner', notification_type='inbox')
        cls.reader = new_test_user(cls.env, login='bus_reader')
        cls.stranger = new_test_user(cls.env, login='bus_stranger')
        cls.session = cls._chat()

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @classmethod
    def _chat(cls, owner: models.BaseModel | None = None) -> models.BaseModel:
        """Create a chat of ``owner`` (the owner by default) shared with the reader."""
        session = (
            cls.env['muk_ai.session']
            .with_user(owner or cls.owner)
            .create({'name': 'Chat', 'override_approval_mode': 'ask'})
        )
        session.sudo().share_user_ids = [Command.set(cls.reader.ids)]
        return session.with_user(owner or cls.owner)

    def _channels(self, user: models.BaseModel, asked: str) -> list:
        """Return the channels the websocket grants ``user`` for ``asked``."""
        request = MagicMock()
        request.session.uid = user.id
        with patch('odoo.addons.bus.models.ir_websocket.wsrequest', new=request):
            websocket = self.env['ir.websocket'].with_user(user)
            return websocket._build_bus_channel_list([asked])

    def _queue_then(
        self, session: models.BaseModel, payload: dict
    ) -> Callable[[dict], dict]:
        """Return a provider answer that queues another message while it runs."""

        def answer(request: dict) -> dict:
            """Queue the message, then answer the round."""
            session.enqueue_message('and also')
            return payload

        return answer

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_the_websocket_grants_a_chat_channel_to_its_readers_only(self):
        asked = f'muk_ai.session_{self.session.id}'
        for label, user, channel, granted, kept in (
            ('owner', self.owner, asked, [self.session.id], False),
            ('reader', self.reader, asked, [self.session.id], False),
            ('stranger', self.stranger, asked, [], False),
            ('missing chat', self.owner, 'muk_ai.session_999999999', [], False),
            ('another channel', self.stranger, 'some.channel', [], True),
        ):
            with self.subTest(label):
                channels = self._channels(user, channel)
                names = [entry for entry in channels if isinstance(entry, str)]
                chats = [
                    entry.id
                    for entry in channels
                    if isinstance(entry, models.BaseModel)
                    and entry._name == 'muk_ai.session'
                ]
                self.assertEqual(chats, granted)
                self.assertEqual(channel in names, kept)

    def test_a_turn_streams_on_the_chat_and_tells_the_owner(self):
        with self._capture_bus() as sent, self._mock_responses([text_payload()]):
            self.session.send_message('Plan the quarter')
        for kind, targets in (
            ('muk_ai.event', {self.session}),
            ('muk_ai.session_state', {self.owner, self.reader}),
            ('muk_ai.session_notification', {self.owner}),
            ('muk_ai.notification_badge', {self.owner}),
        ):
            with self.subTest(kind):
                self.assertEqual(
                    {
                        target
                        for target, sent_kind, _message in sent
                        if sent_kind == kind
                    },
                    targets,
                )

    def test_the_chat_list_follows_who_may_read_the_chat(self):
        for label, change, user, deleted in (
            (
                'reader added',
                lambda chat: chat.write(
                    {'share_user_ids': [Command.link(self.stranger.id)]}
                ),
                self.stranger,
                False,
            ),
            (
                'reader dropped',
                lambda chat: chat.write(
                    {'share_user_ids': [Command.unlink(self.reader.id)]}
                ),
                self.reader,
                True,
            ),
            (
                'handed to the reader',
                lambda chat: chat.action_handover(self.reader.id),
                self.reader,
                False,
            ),
            ('deleted', lambda chat: chat.unlink(), self.reader, True),
        ):
            with self.subTest(label):
                session = self._chat()
                session_id = session.id
                with self._capture_bus() as sent:
                    change(session)
                told = [
                    message
                    for target, kind, message in sent
                    if kind == 'muk_ai.session_state' and target == user
                ]
                self.assertEqual(
                    {
                        (message['session_id'], bool(message.get('deleted')))
                        for message in told
                    },
                    {(session_id, deleted)},
                )

    def test_a_settled_turn_toasts_its_owner_and_only_a_wait_reaches_the_inbox(self):
        self._mark_sensitive('res.partner')
        partner = self.env['res.partner'].create({'name': 'Customer'})
        update = {'model': 'res.partner', 'ids': [partner.id], 'values': {'name': 'X'}}
        for label, owner, payload, message, inboxed in (
            ('done', self.owner, text_payload(), 'Finished', False),
            (
                'waiting for an answer',
                self.owner,
                tool_payload(('ask_user', {'question': 'Which year?'})),
                'Waiting for your answer',
                True,
            ),
            (
                'waiting for approval, email user',
                self.stranger,
                tool_payload(('update_records', update)),
                'Needs your approval before running a tool',
                False,
            ),
            (
                'error',
                self.owner,
                UserError('provider down'),
                'Stopped: provider down',
                False,
            ),
        ):
            with self.subTest(label):
                session = self._chat(owner)
                with self._capture_bus() as sent, self._mock_responses([payload]):
                    session.send_message('Plan the quarter')
                toasts = [
                    (target, body['session_name'], body['message'])
                    for target, kind, body in sent
                    if kind == 'muk_ai.session_notification'
                ]
                self.assertEqual(toasts, [(owner, session.name, message)])
                self.assertTrue(session.notification_unread)
                inbox = self.env['mail.message'].search(
                    [
                        ('muk_ai_session_id', '=', session.id),
                        ('notification_ids.res_partner_id', '=', owner.partner_id.id),
                    ]
                )
                self.assertEqual(
                    inbox.mapped('subject'), [session.name] if inboxed else []
                )
                self.assertEqual(
                    inbox.notification_ids.res_partner_id,
                    owner.partner_id if inboxed else owner.partner_id.browse(),
                )

    def test_a_turn_with_more_to_come_stays_quiet(self):
        for label, context, queued, toasts in (
            ('nothing follows', {}, False, ['done']),
            ('told to stay quiet', {'muk_ai_skip_done_notification': True}, False, []),
            ('a queued message follows', {}, True, ['done']),
        ):
            with self.subTest(label):
                session = self._chat()
                payloads = [text_payload('first')]
                if queued:
                    payloads = [self._queue_then(session, payloads[0]), text_payload()]
                with (
                    self._capture_bus() as sent,
                    self._mock_responses(payloads) as requests,
                ):
                    session.with_context(**context).send_message('Plan the quarter')
                self.assertEqual(len(requests), len(payloads))
                self.assertEqual(
                    [
                        body['state']
                        for _target, kind, body in sent
                        if kind == 'muk_ai.session_notification'
                    ],
                    toasts,
                )
                self.assertEqual(session.notification_unread, bool(toasts))

    def test_the_badge_counts_unread_chats_until_they_are_opened(self):
        first, second = self._chat(), self._chat()
        question = tool_payload(('ask_user', {'question': 'Which year?'}))
        with self._mock_responses([question, question]):
            first.send_message('one')
            second.send_message('two')
        sessions = self.env['muk_ai.session']
        badge = sessions.with_user(self.owner).notification_badge()
        self.assertEqual(badge['count'], 2)
        self.assertEqual(set(badge['session_ids']), {first.id, second.id})
        self.assertEqual(
            sessions.with_user(self.reader).notification_badge()['count'], 0
        )
        with self._capture_bus() as sent:
            first.dismiss_notifications()
        self.assertEqual(
            [
                message['session_ids']
                for target, kind, message in sent
                if kind == 'muk_ai.notification_badge' and target == self.owner
            ],
            [[second.id]],
        )
        self.assertFalse(first.notification_unread)
        notified = self.env['mail.message'].search(
            [
                ('muk_ai_session_id', 'in', [first.id, second.id]),
                ('notification_ids.res_partner_id', '=', self.owner.partner_id.id),
            ]
        )
        self.assertEqual(
            {
                message.muk_ai_session_id: message.notification_ids.is_read
                for message in notified
            },
            {first: True, second: False},
        )
