from __future__ import annotations

from odoo import Command, models
from odoo.exceptions import AccessError, UserError
from odoo.tests import new_test_user

from odoo.addons.muk_ai.tests.common import AITestCommon


class TestShare(AITestCommon):
    """Verify a shared chat is read by its readers and steered by its owner alone."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        """Create the owner, the reader, a stranger and their shared chat."""
        super().setUpClass()
        cls.owner = new_test_user(cls.env, login='share_owner')
        cls.reader = new_test_user(
            cls.env, login='share_reader', notification_type='inbox'
        )
        cls.stranger = new_test_user(cls.env, login='share_stranger')
        cls.session = cls._chat()

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @classmethod
    def _chat(cls, state: str = 'done') -> models.BaseModel:
        """Create a chat of the owner that is shared with the reader."""
        session = (
            cls.env['muk_ai.session'].with_user(cls.owner).create({'name': 'Chat'})
        )
        session.sudo().write(
            {
                'state': state,
                'conversation': [{'role': 'assistant', 'content': 'secret output'}],
                'share_user_ids': [Command.set(cls.reader.ids)],
            }
        )
        return session

    def _event(self, session: models.BaseModel, **values) -> models.BaseModel:
        """Append a line to the transcript of ``session``."""
        return self.env['muk_ai.session.event'].create(
            {
                'session_id': session.id,
                'sequence': len(session.sudo().event_ids),
                'kind': 'note',
                'payload': {'kind': 'note', 'content': 'noted'},
                **values,
            }
        )

    def _footprint(self) -> tuple:
        """Return everything a steering call could leave behind on the chat."""
        session = self.session.sudo()
        session.invalidate_recordset()
        return (
            session.name,
            session.state,
            session.conversation,
            session.pending_ask,
            session.view_context,
            session.override_approval_mode,
            session.override_reasoning_effort,
            session.share_user_ids.ids,
            session.attachment_ids.ids,
            session.pending_ids.ids,
            session.event_ids.ids,
            self.env['muk_ai.approval'].search_count([('session_id', '=', session.id)]),
        )

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_the_share_list_decides_who_reads_the_chat(self):
        for label, user, unshare, readable in (
            ('owner', self.owner, False, True),
            ('reader', self.reader, False, True),
            ('stranger', self.stranger, False, False),
            ('reader after unsharing', self.reader, True, False),
        ):
            with self.subTest(label):
                if unshare:
                    self.session.with_user(self.owner).write(
                        {'share_user_ids': [Command.clear()]}
                    )
                found = (
                    self.env['muk_ai.session']
                    .with_user(user)
                    .search([('id', '=', self.session.id)])
                )
                self.assertEqual(found.ids, [self.session.id] if readable else [])
                chat = self.session.with_user(user)
                if readable:
                    read = chat.read(['conversation'])[0]['conversation']
                    self.assertEqual(read[0]['content'], 'secret output')
                else:
                    with self.assertRaises(AccessError):
                        chat.read(['name'])

    def test_a_reader_is_refused_before_a_steering_call_does_anything(self):
        event = self._event(self.session)
        self.env['muk_ai.session.pending'].create(
            {'session_id': self.session.id, 'content': 'queued by the owner'}
        )
        attachment = self.env['ir.attachment'].create(
            {
                'name': 'upload.txt',
                'res_model': 'muk_ai.session',
                'res_id': self.session.id,
            }
        )
        calls = (
            ('write', lambda chat: chat.write({'name': 'renamed'})),
            ('unlink', lambda chat: chat.unlink()),
            (
                'share further',
                lambda chat: chat.write(
                    {'share_user_ids': [Command.link(self.stranger.id)]}
                ),
            ),
            ('start', lambda chat: chat.start('hello')),
            ('send_message', lambda chat: chat.send_message('hello')),
            ('enqueue_message', lambda chat: chat.enqueue_message('more')),
            ('cancel_queued', lambda chat: chat.cancel_queued(0)),
            ('answer', lambda chat: chat.answer('42')),
            ('regenerate_last_turn', lambda chat: chat.regenerate_last_turn()),
            ('clear', lambda chat: chat.clear()),
            ('compact', lambda chat: chat.compact()),
            ('stop_compact', lambda chat: chat.stop_compact()),
            ('undo_to_event', lambda chat: chat.undo_to_event(event.id)),
            ('fork_at_event', lambda chat: chat.fork_at_event(event.id)),
            ('set_view_context', lambda chat: chat.set_view_context({'kind': 'none'})),
            ('unpin_view_context', lambda chat: chat.unpin_view_context()),
            ('set_approval_mode', lambda chat: chat.set_approval_mode('off')),
            ('set_reasoning_effort', lambda chat: chat.set_reasoning_effort('low')),
            ('approve_tool', lambda chat: chat.approve_tool()),
            ('approve_for_session', lambda chat: chat.approve_for_session()),
            ('reject_tool', lambda chat: chat.reject_tool('no')),
            ('submit_client_result', lambda chat: chat.submit_client_result('c1', {})),
            ('reject_client_action', lambda chat: chat.reject_client_action()),
            ('upload_attachments', lambda chat: chat.upload_attachments([])),
            (
                'discard_attachments',
                lambda chat: chat.discard_attachments([attachment.id]),
            ),
        )
        before = self._footprint()
        for name, call in calls:
            with self.subTest(name), self.assertRaises(AccessError):
                call(self.session.with_user(self.reader))
            self.assertEqual(self._footprint(), before)

    def test_a_reader_follows_the_chat_without_taking_it_over(self):
        self.session.sudo().notification_unread = True
        self.env['muk_ai.session.pending'].create(
            {'session_id': self.session.id, 'content': 'queued'}
        )
        for user, can_write, queue, unread in (
            (self.reader, False, [], True),
            (self.owner, True, ['queued'], False),
        ):
            with self.subTest(user=user.login):
                chat = self.session.with_user(user)
                snapshot = chat.get_snapshot()
                self.assertEqual(snapshot['can_write'], can_write)
                self.assertEqual(
                    [row['content'] for row in snapshot['pending_user_messages']],
                    queue,
                )
                chat.dismiss_notifications()
                self.assertEqual(self.session.sudo().notification_unread, unread)

    def test_shared_with_me_collects_what_others_share(self):
        shared = self.env.ref('muk_ai.space_shared')
        space = self.env['muk_ai.space'].with_user(self.owner).create({'name': 'Mine'})
        for label, filed, user, in_shared, in_general in (
            ('reader', False, self.reader, True, False),
            ('owner', False, self.owner, False, True),
            ('reader, filed by the owner', True, self.reader, True, False),
            ('owner, filed', True, self.owner, False, False),
        ):
            with self.subTest(label):
                self.session.with_user(self.owner).space_id = filed and space
                spaces = self.env['muk_ai.space'].with_user(user)
                sessions = self.env['muk_ai.session'].with_user(user)
                entry = next(
                    row for row in spaces.fetch_spaces() if row['id'] == shared.id
                )
                found = sessions.search(entry['session_domain'])
                general = sessions.search(spaces.fetch_general_domain())
                self.assertEqual(self.session in found, in_shared)
                self.assertEqual(self.session in general, in_general)

    def test_a_handover_makes_the_giver_a_reader(self):
        manager = new_test_user(
            self.env, login='share_manager', groups='base.group_system'
        )
        for actor in (self.owner, manager):
            with self.subTest(actor=actor.login):
                session = self._chat()
                session.sudo().approved_signatures = ['update_records:res.partner']
                self._event(session, private_user_id=self.owner.id)
                session.with_user(actor).action_handover(self.reader.id)
                self.assertEqual(session.sudo().user_id, self.reader)
                self.assertEqual(session.sudo().share_user_ids, self.owner)
                self.assertFalse(session.sudo().approved_signatures)
                for user, can_write, kinds in (
                    (self.reader, True, []),
                    (self.owner, False, ['note']),
                ):
                    chat = session.with_user(user)
                    self.assertEqual(chat.can_write, can_write)
                    self.assertEqual(
                        [event['kind'] for event in chat.fetch_events()['events']],
                        kinds,
                    )
                with self.assertRaises(AccessError):
                    session.with_user(self.owner).write({'name': 'mine again'})

    def test_a_handover_is_refused(self):
        portal = new_test_user(
            self.env, login='share_portal', groups='base.group_portal'
        )
        retired = new_test_user(self.env, login='share_retired')
        retired.active = False
        for label, actor, target, state, error in (
            ('by a reader', self.reader, self.stranger, 'done', AccessError),
            ('to a portal user', self.owner, portal, 'done', UserError),
            ('to an inactive user', self.owner, retired, 'done', UserError),
            ('while running', self.owner, self.stranger, 'running', UserError),
        ):
            with self.subTest(label):
                session = self._chat(state)
                with self.assertRaises(error):
                    session.with_user(actor).action_handover(target.id)
                self.assertEqual(session.sudo().user_id, self.owner)

    def test_a_handover_tells_both_users(self):
        session = self._chat()
        with self._capture_bus() as sent:
            session.with_user(self.owner).action_handover(self.reader.id)
        badges = {
            target: message
            for target, kind, message in sent
            if kind == 'muk_ai.notification_badge'
        }
        self.assertEqual(
            badges,
            {
                self.reader: {
                    'count': 1,
                    'session_ids': [session.id],
                    'space_unread': {},
                },
                self.owner: {'count': 0, 'session_ids': [], 'space_unread': {}},
            },
        )
        told = [
            message
            for target, kind, message in sent
            if kind in ('muk_ai.session_state', 'muk_ai.session_notification')
            and target == self.reader
        ]
        self.assertEqual([message.get('deleted') for message in told], [None])
        notice = self.env['mail.message'].search(
            [('muk_ai_session_id', '=', session.id)], order='id desc', limit=1
        )
        self.assertEqual(
            notice.notification_ids.mapped('res_partner_id'), self.reader.partner_id
        )
        self.assertEqual(notice.subject, 'Chat handed over to you')
        self.assertIn(f'{self.owner.name} handed you the chat', notice.body)

    def test_sharing_tells_each_new_reader_the_way_they_prefer(self):
        session = self._chat()
        notices = self.env['mail.message'].search(
            [('muk_ai_session_id', '=', session.id)]
        )
        for label, user, command, kind in (
            (
                'an inbox reader',
                new_test_user(self.env, login='share_inbox', notification_type='inbox'),
                Command.link,
                'inbox',
            ),
            (
                'an email reader',
                new_test_user(self.env, login='share_mail', notification_type='email'),
                Command.link,
                'email',
            ),
            ('a removed reader', self.reader, Command.unlink, None),
        ):
            with self.subTest(label):
                session.with_user(self.owner).write(
                    {'share_user_ids': [command(user.id)]}
                )
                new = self.env['mail.message'].search(
                    [
                        ('muk_ai_session_id', '=', session.id),
                        ('id', 'not in', notices.ids),
                    ]
                )
                notices |= new
                self.assertEqual(
                    new.notification_ids.mapped(
                        lambda line: (line.res_partner_id, line.notification_type)
                    ),
                    [(user.partner_id, kind)] if kind else [],
                )
                if kind:
                    self.assertIn(f'{self.owner.name} shared the chat', new.body)
