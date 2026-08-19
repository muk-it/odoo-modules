from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from odoo import models
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user


@tagged('post_install', '-at_install', 'muk_ai')
class TestSessionBus(TransactionCase):
    """Verify which channel each kind of session notification travels on."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.owner = new_test_user(cls.env, login='bus_owner', groups='base.group_user')
        cls.reader = new_test_user(
            cls.env, login='bus_reader', groups='base.group_user'
        )
        cls.stranger = new_test_user(
            cls.env, login='bus_stranger', groups='base.group_user'
        )
        cls.session = (
            cls.env['muk_ai.session'].with_user(cls.owner).create({'name': 'Streamed'})
        )
        cls.session.sudo().write({'share_user_ids': [(6, 0, cls.reader.ids)]})

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @contextmanager
    def _captured(self) -> Iterator[list]:
        """Collect every ``(target, type, message)`` sent on the bus."""
        captured = []

        def fake(_self, target, notification_type, message):
            captured.append((target, notification_type, message))

        with patch.object(
            type(self.env['bus.bus']), '_sendone', autospec=True, side_effect=fake
        ):
            yield captured

    def _targets(self, captured: list, notification_type: str) -> list:
        """Return the targets a notification type was sent to."""
        return [
            target for target, ntype, _message in captured if ntype == notification_type
        ]

    def _session_channels(self, channels: list) -> list:
        """Return the chat records among the granted channels."""
        return [
            channel
            for channel in channels
            if isinstance(channel, models.Model) and channel._name == 'muk_ai.session'
        ]

    def _channel_names(self, channels: list) -> list:
        """Return the plainly named channels among the granted channels."""
        return [channel for channel in channels if isinstance(channel, str)]

    def _channels(self, user: models.Model, asked: list) -> list:
        """Return the channels the websocket grants the given user.

        The core builder reads the websocket request for the caller, which a
        plain transaction has none of, so it is stood in for the same way
        Odoo tests its own builder. Mail wraps the builder to pick a guest out
        of the request cookies, so the stand-in carries a cookie jar and an
        environment as well, and mail's own module globals are pointed at it —
        it imported both names before the patch could reach them.
        """
        request = MagicMock()
        request.session.uid = user.id
        request.cookies = {}
        request.env = self.env(user=user)
        with (
            patch('odoo.addons.bus.models.ir_websocket.wsrequest', new=request),
            patch('odoo.addons.mail.models.discuss.mail_guest.request', new=None),
            patch('odoo.addons.mail.models.discuss.mail_guest.wsrequest', new=request),
        ):
            return (
                self.env['ir.websocket']
                .with_user(user)
                ._build_bus_channel_list(list(asked))
            )

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_the_transcript_rides_the_session_channel(self):
        with self._captured() as captured:
            self.session._publish_event('text_delta', {'delta': 'hi'})
        self.assertEqual(self._targets(captured, 'muk_ai.event'), [self.session])

    def test_the_sidebar_state_reaches_the_owner_and_the_readers(self):
        with self._captured() as captured:
            self.session._publish_event('rename', {'name': 'Renamed'})
        self.assertEqual(
            set(self._targets(captured, 'muk_ai.session_state')),
            {self.owner.partner_id, self.reader.partner_id},
        )

    def test_a_deletion_reaches_the_readers_too(self):
        session = self.env['muk_ai.session'].with_user(self.owner).create({'name': 'X'})
        session.sudo().write({'share_user_ids': [(6, 0, self.reader.ids)]})
        with self._captured() as captured:
            session.sudo().unlink()
        self.assertIn(
            self.reader.partner_id, self._targets(captured, 'muk_ai.session_state')
        )

    def test_the_finished_toast_stays_with_the_owner(self):
        with self._captured() as captured:
            self.session._notify_state_transition({'state': 'done'})
        self.assertEqual(
            self._targets(captured, 'muk_ai.session_notification'),
            [self.owner.partner_id],
        )

    def test_a_reader_may_follow_the_chat_channel(self):
        channels = self._channels(self.reader, [f'muk_ai.session_{self.session.id}'])
        self.assertIn(self.session, self._session_channels(channels))

    def test_a_stranger_may_not_follow_the_chat_channel(self):
        channels = self._channels(self.stranger, [f'muk_ai.session_{self.session.id}'])
        self.assertNotIn(self.session, self._session_channels(channels))

    def test_the_name_a_stranger_asked_for_is_never_kept(self):
        asked = f'muk_ai.session_{self.session.id}'
        channels = self._channels(self.stranger, [asked])
        self.assertNotIn(asked, self._channel_names(channels))

    def test_a_chat_that_does_not_exist_grants_nothing(self):
        channels = self._channels(self.owner, ['muk_ai.session_999999999'])
        self.assertFalse(self._session_channels(channels))

    def test_an_unrelated_channel_is_left_alone(self):
        channels = self._channels(self.owner, ['some.other_channel'])
        self.assertIn('some.other_channel', self._channel_names(channels))

    def test_dropping_a_reader_takes_the_chat_off_their_list(self):
        with self._captured() as captured:
            self.session.with_user(self.owner).write({'share_user_ids': [(5, 0, 0)]})
        dropped = [
            message
            for target, ntype, message in captured
            if ntype == 'muk_ai.session_state' and target == self.reader.partner_id
        ]
        self.assertTrue(dropped)
        self.assertTrue(dropped[-1].get('deleted'))

    def test_adding_a_reader_puts_the_chat_on_their_list(self):
        with self._captured() as captured:
            self.session.with_user(self.owner).write(
                {'share_user_ids': [(4, self.stranger.id)]}
            )
        added = [
            message
            for target, ntype, message in captured
            if ntype == 'muk_ai.session_state' and target == self.stranger.partner_id
        ]
        self.assertTrue(added)
        self.assertFalse(added[-1].get('deleted'))
        self.assertEqual(added[-1]['session_id'], self.session.id)

    def test_handing_the_chat_to_a_reader_never_tells_them_it_went_away(self):
        with self._captured() as captured:
            self.session.with_user(self.owner).action_handover(self.reader.id)
        told = [
            message
            for target, ntype, message in captured
            if ntype == 'muk_ai.session_state' and target == self.reader.partner_id
        ]
        self.assertFalse([message for message in told if message.get('deleted')])
