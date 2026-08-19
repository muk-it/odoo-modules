from __future__ import annotations

from odoo import models
from odoo.exceptions import AccessError
from odoo.osv.expression import AND
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
            .search(AND([general, [('user_id', '=', self.owner.id)]]))
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
