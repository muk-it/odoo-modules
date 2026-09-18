from __future__ import annotations

from odoo import models
from odoo.exceptions import AccessError
from odoo.osv import expression
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user


@tagged('post_install', '-at_install', 'muk_ai')
class TestShare(TransactionCase):
    """Verify that a shared chat is readable by its readers and nobody else."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.owner = new_test_user(
            cls.env, login='share_owner', groups='base.group_user'
        )
        cls.reader = new_test_user(
            cls.env, login='share_reader', groups='base.group_user'
        )
        cls.stranger = new_test_user(
            cls.env, login='share_stranger', groups='base.group_user'
        )
        cls.session = (
            cls.env['muk_ai.session']
            .with_user(cls.owner)
            .create({'name': 'Shared chat'})
        )
        cls.session.sudo().write(
            {
                'conversation': [{'role': 'assistant', 'content': 'secret output'}],
                'share_user_ids': [(6, 0, cls.reader.ids)],
            }
        )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _as(self, user: models.Model) -> models.Model:
        """Return the shared session read as the given user."""
        return self.session.with_user(user)

    def _footprint(self) -> tuple:
        """Return everything a steering call leaves behind on the chat."""
        session = self.session.sudo()
        session.invalidate_recordset()
        return (
            session.state,
            session.conversation,
            session.pending_ask,
            session.view_context,
            session.override_approval_mode,
            session.override_reasoning_effort,
            session.attachment_ids.ids,
            session.pending_ids.ids,
            self.env['muk_ai.session.event']
            .sudo()
            .search_count([('session_id', '=', session.id)]),
            self.env['muk_ai.approval']
            .sudo()
            .search_count([('session_id', '=', session.id)]),
        )

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_a_reader_sees_the_whole_transcript(self):
        read = self._as(self.reader).read(['name', 'conversation'])[0]
        self.assertEqual(read['name'], 'Shared chat')
        self.assertEqual(read['conversation'][0]['content'], 'secret output')

    def test_a_reader_finds_it_in_a_search(self):
        found = (
            self.env['muk_ai.session']
            .with_user(self.reader)
            .search([('id', '=', self.session.id)])
        )
        self.assertEqual(found.ids, [self.session.id])

    def test_a_reader_cannot_write_to_it(self):
        with self.assertRaises(AccessError):
            self._as(self.reader).write({'name': 'renamed'})

    def test_a_reader_cannot_delete_it(self):
        with self.assertRaises(AccessError):
            self._as(self.reader).unlink()

    def test_a_reader_cannot_share_it_further(self):
        with self.assertRaises(AccessError):
            self._as(self.reader).write({'share_user_ids': [(4, self.stranger.id)]})

    def test_a_stranger_still_sees_nothing(self):
        found = (
            self.env['muk_ai.session']
            .with_user(self.stranger)
            .search([('id', '=', self.session.id)])
        )
        self.assertFalse(found)
        with self.assertRaises(AccessError):
            self._as(self.stranger).read(['name'])

    def test_unsharing_takes_the_chat_back(self):
        self.session.with_user(self.owner).write({'share_user_ids': [(5, 0, 0)]})
        with self.assertRaises(AccessError):
            self._as(self.reader).read(['name'])

    def test_the_shared_space_collects_it_for_the_reader(self):
        space = self.env.ref('muk_ai.space_shared')
        found = (
            self.env['muk_ai.session']
            .with_user(self.reader)
            .search(space.with_user(self.reader)._session_domain())
        )
        self.assertIn(self.session.id, found.ids)

    def test_the_shared_space_keeps_a_chat_the_owner_filed_away(self):
        space = self.env['muk_ai.space'].with_user(self.owner).create({'name': 'Mine'})
        self.session.with_user(self.owner).write({'space_id': space.id})
        shared = self.env.ref('muk_ai.space_shared')
        found = (
            self.env['muk_ai.session']
            .with_user(self.reader)
            .search(shared.with_user(self.reader)._session_domain())
        )
        self.assertIn(self.session.id, found.ids)

    def test_filing_a_chat_keeps_it_for_the_people_it_is_shared_with(self):
        space = self.env['muk_ai.space'].with_user(self.owner).create({'name': 'Mine'})
        own = self.env['muk_ai.session'].with_user(self.owner).create({'name': 'Own'})
        own.write({'share_user_ids': [(6, 0, self.stranger.ids)]})
        shared = self.env.ref('muk_ai.space_shared')
        domain = shared.with_user(self.stranger)._session_domain()
        Session = self.env['muk_ai.session'].with_user(self.stranger)
        self.assertIn(own.id, Session.search(domain).ids)
        own.with_user(self.owner).write({'space_id': space.id})
        self.assertIn(own.id, Session.search(domain).ids)

    def test_reading_a_shared_chat_leaves_the_owner_notification_alone(self):
        self.session.sudo().write({'notification_unread': True})
        self._as(self.reader).dismiss_notifications()
        self.assertTrue(self.session.sudo().notification_unread)

    def test_the_owner_dismisses_their_own_notification(self):
        self.session.sudo().write({'notification_unread': True})
        self.session.with_user(self.owner).dismiss_notifications()
        self.assertFalse(self.session.sudo().notification_unread)

    def test_a_reader_cannot_fork_the_chat(self):
        with self.assertRaises(AccessError):
            self._as(self.reader).fork_at_event(1)

    def test_a_reader_is_refused_before_a_steering_call_does_anything(self):
        event = self.session.sudo()._append_event(
            {'kind': 'command', 'name': '/noop', 'message': 'noop'}
        )
        self.session.sudo().pending_ids.create(
            {'session_id': self.session.id, 'content': 'queued by the owner'}
        )
        calls = (
            ('enqueue_message', ('more',)),
            ('start', ('hello',)),
            ('answer', ('42',)),
            ('send_message', ('hello',)),
            ('regenerate_last_turn', ()),
            ('clear', ()),
            ('compact', ()),
            ('stop_compact', ()),
            ('undo_to_event', (event.id,)),
            ('set_view_context', ({'kind': 'none'},)),
            ('unpin_view_context', ()),
            ('set_approval_mode', ('off',)),
            ('set_reasoning_effort', (None,)),
            ('approve_tool', ()),
            ('approve_for_session', ()),
            ('reject_tool', ('no',)),
            ('submit_client_result', ('c1', {})),
            ('reject_client_action', ()),
            ('upload_attachments', ([],)),
            ('discard_attachments', ([],)),
            ('fork_at_event', (event.id,)),
        )
        before = self._footprint()
        for name, args in calls:
            with self.subTest(method=name), self.assertRaises(AccessError):
                getattr(self._as(self.reader), name)(*args)
            self.assertEqual(self._footprint(), before)

    def test_a_reader_still_reads_the_chat_and_sees_no_queue(self):
        queued = self.session.sudo().pending_ids.create(
            {'session_id': self.session.id, 'content': 'queued by the owner'}
        )
        reader = self._as(self.reader)
        snapshot = reader.get_snapshot()
        self.assertEqual(snapshot['id'], self.session.id)
        self.assertFalse(snapshot['can_write'])
        self.assertEqual(snapshot['pending_user_messages'], [])
        self.assertIn('events', reader.fetch_events())
        self.assertIn('count', reader.notification_badge())
        # Refused outright rather than quietly doing nothing: whether it
        # would have found a row depended on what was already in the cache.
        with self.assertRaises(AccessError):
            reader.cancel_queued(0)
        self.assertTrue(queued.exists())

    def test_the_shared_space_leaves_the_owner_their_own_chat(self):
        space = self.env.ref('muk_ai.space_shared')
        found = (
            self.env['muk_ai.session']
            .with_user(self.owner)
            .search(space.with_user(self.owner)._session_domain())
        )
        self.assertNotIn(self.session.id, found.ids)

    def test_the_owner_still_finds_a_chat_they_shared_out(self):
        general = (
            self.env['muk_ai.space'].with_user(self.owner)._unclaimed_session_domain()
        )
        found = (
            self.env['muk_ai.session']
            .with_user(self.owner)
            .search(expression.AND([general, [('user_id', '=', self.owner.id)]]))
        )
        self.assertIn(self.session.id, found.ids)

    def test_a_chat_shared_with_me_leaves_my_general_list(self):
        general = (
            self.env['muk_ai.space'].with_user(self.reader)._unclaimed_session_domain()
        )
        found = self.env['muk_ai.session'].with_user(self.reader).search(general)
        self.assertNotIn(self.session.id, found.ids)

    def test_handing_over_keeps_the_giver_as_a_reader(self):
        session = (
            self.env['muk_ai.session']
            .with_user(self.owner)
            .create({'name': 'Handed over'})
        )
        session.with_user(self.owner).action_handover(self.stranger.id)
        self.assertEqual(session.sudo().user_id, self.stranger)
        self.assertIn(self.owner, session.sudo().share_user_ids)
        self.assertEqual(
            session.with_user(self.owner).read(['name'])[0]['name'], 'Handed over'
        )

    def test_handing_over_drops_the_taker_from_the_share_list(self):
        session = (
            self.env['muk_ai.session']
            .with_user(self.owner)
            .create({'name': 'Handed back'})
        )
        session.sudo().write({'share_user_ids': [(6, 0, self.stranger.ids)]})
        session.with_user(self.owner).action_handover(self.stranger.id)
        self.assertNotIn(self.stranger, session.sudo().share_user_ids)
