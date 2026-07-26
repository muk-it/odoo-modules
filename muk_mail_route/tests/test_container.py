from __future__ import annotations

from odoo.tests import tagged
from odoo.tests.common import new_test_user

from odoo.addons.mail.tests.common import MailCommon


@tagged('post_install', '-at_install')
class TestContainer(MailCommon):
    """Test the singleton failure container and its follower handling."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.container = cls.env['mail.thread']._get_failed_route_container()

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_container_is_reused_instead_of_recreated(self):
        again = self.env['mail.thread']._get_failed_route_container()
        self.assertEqual(again, self.container)
        self.assertEqual(
            self.env['muk_mail_route.container'].search([]), self.container
        )

    def test_existing_followers_are_dropped(self):
        partner = self.env['res.partner'].create({'name': 'Curious Follower'})
        self.container.message_subscribe(partner_ids=partner.ids)
        self.assertTrue(self.container.message_follower_ids)
        self.env['mail.thread']._get_failed_route_container()
        self.assertFalse(self.container.message_follower_ids)

    def test_posting_does_not_subscribe_the_author(self):
        user = new_test_user(self.env, 'container_poster', groups='base.group_user')
        self.container.with_user(user).sudo().message_post(
            body='<p>Lost mail</p>',
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
        )
        self.assertFalse(self.container.message_follower_ids)

    def test_posting_does_not_autofollow_recipients(self):
        partner = self.env['res.partner'].create({'name': 'Mentioned Partner'})
        self.container.message_post(
            body='<p>Lost mail</p>',
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
            partner_ids=partner.ids,
        )
        self.assertFalse(self.container.message_follower_ids)

    def test_display_name_is_the_static_label(self):
        self.assertEqual(self.container.display_name, 'Message Container')
