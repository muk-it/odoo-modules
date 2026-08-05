from __future__ import annotations

from unittest.mock import patch

from odoo.tests.common import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestMailThread(TransactionCase):
    """Cover the recipients added when notifying the internal followers."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.internal_user = new_test_user(
            cls.env,
            login='chatter_internal',
            groups='base.group_user',
        )
        cls.portal_user = new_test_user(
            cls.env,
            login='chatter_portal',
            groups='base.group_portal',
        )
        cls.contact = cls.env['res.partner'].create({'name': 'Chatter Contact'})
        cls.record = cls.env['res.partner'].create({'name': 'Chatter Record'})
        cls.followers = (
            cls.internal_user.partner_id | cls.portal_user.partner_id | cls.contact
        )
        cls.record.message_subscribe(partner_ids=cls.followers.ids)
        cls.internal_record = cls.record.with_context(
            mail_notify_internal_followers=True
        )

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_internal_followers_ignore_portal_and_contact_followers(self):
        self.assertEqual(
            self.record._get_internal_follower_partners(),
            self.internal_user.partner_id,
        )

    def test_note_notifies_the_internal_followers(self):
        message = self.internal_record.message_post(
            body='Internal update', subtype_xmlid='mail.mt_note'
        )
        self.assertEqual(message.partner_ids, self.internal_user.partner_id)

    def test_note_without_the_context_keeps_no_recipient(self):
        message = self.record.message_post(
            body='Plain note', subtype_xmlid='mail.mt_note'
        )
        self.assertFalse(message.partner_ids)

    def test_note_merges_the_explicit_recipients(self):
        message = self.internal_record.message_post(
            body='Internal update',
            subtype_xmlid='mail.mt_note',
            partner_ids=self.contact.ids,
        )
        self.assertEqual(
            message.partner_ids, self.internal_user.partner_id | self.contact
        )

    def test_note_from_a_portal_user_adds_no_recipient(self):
        record = self.record.with_user(self.portal_user).sudo()
        message = record.with_context(mail_notify_internal_followers=True).message_post(
            body='Portal note', subtype_xmlid='mail.mt_note'
        )
        self.assertFalse(message.partner_ids)

    def test_note_does_not_leak_the_notification_to_nested_posts(self):
        nested = self.env['mail.message']
        posted = False

        def post_after_hook(record, message, msg_vals):
            nonlocal nested, posted
            if posted:
                return
            posted = True
            nested = record.message_post(
                body='Nested note', subtype_xmlid='mail.mt_note'
            )

        with patch.object(
            type(self.record), '_message_post_after_hook', post_after_hook
        ):
            self.internal_record.message_post(
                body='Internal update', subtype_xmlid='mail.mt_note'
            )
        self.assertTrue(nested)
        self.assertFalse(nested.partner_ids)

    def test_note_skips_the_author(self):
        message = self.internal_record.with_user(self.internal_user).message_post(
            body='Internal update', subtype_xmlid='mail.mt_note'
        )
        self.assertFalse(message.partner_ids)
