from __future__ import annotations

from unittest.mock import patch

from odoo import models
from odoo.tests import TransactionCase, new_test_user


class TestMailThread(TransactionCase):
    """Cover the recipients added when notifying the internal followers."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        """Create the users and the records the notifications are posted on."""
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
        cls.record.message_subscribe(
            partner_ids=(
                cls.internal_user.partner_id | cls.portal_user.partner_id | cls.contact
            ).ids
        )
        cls.internal_record = cls.record.with_context(
            mail_notify_internal_followers=True
        )

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_note_recipients(self):
        internal = self.internal_user.partner_id
        cases = [
            ('internal followers only', self.internal_record, [], internal),
            ('without the context', self.record, [], self.env['res.partner']),
            (
                'explicit recipients kept',
                self.internal_record,
                self.contact.ids,
                internal | self.contact,
            ),
            (
                'portal author',
                self.internal_record.with_user(self.portal_user).sudo(),
                [],
                self.env['res.partner'],
            ),
            (
                'author skipped',
                self.internal_record.with_user(self.internal_user),
                [],
                self.env['res.partner'],
            ),
        ]
        for label, record, partner_ids, expected in cases:
            with self.subTest(label):
                message = record.message_post(
                    body=label, subtype_xmlid='mail.mt_note', partner_ids=partner_ids
                )
                self.assertEqual(message.partner_ids, expected)

    def test_note_does_not_leak_the_notification_to_nested_posts(self):
        nested = self.env['mail.message']
        posted = False

        def post_after_hook(
            record: models.BaseModel, message: models.BaseModel
        ) -> None:
            """Post a nested note the first time the hook runs."""
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
