from __future__ import annotations

from email.header import Header

from odoo.tests import tagged

from .common import MAIL_TEMPLATE_ATTACHMENT, MailRouteCommon
from odoo.addons.mail.tests.common import mail_new_test_user


@tagged('post_install', '-at_install')
class TestRoutingFallback(MailRouteCommon):
    """Test that mails without a valid route land in the failure container."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.container = cls.env['mail.thread']._get_failed_route_container()
        cls.catchall = f'{cls.alias_catchall}@{cls.alias_domain}'
        cls.bounce = f'{cls.alias_bounce}@{cls.alias_domain}'

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_unknown_recipient_routes_to_container(self):
        routes = self._route_email(self._build_email(to='sales@unknown.example.com'))
        self.assertEqual(len(routes), 1)
        model, thread_id, _values, _user_id, alias = routes[0]
        self.assertEqual(model, 'muk_mail_route.container')
        self.assertEqual(thread_id, self.container.id)
        self.assertFalse(alias)

    def test_catchall_recipient_routes_to_container(self):
        routes = self._route_email(self._build_email(to=self.catchall))
        self.assertEqual(len(routes), 1)
        self.assertEqual(routes[0][0], 'muk_mail_route.container')
        self.assertEqual(routes[0][1], self.container.id)

    def test_bounce_recipient_routes_to_container(self):
        routes = self._route_email(self._build_email(to=self.bounce))
        self.assertEqual(len(routes), 1)
        self.assertEqual(routes[0][0], 'muk_mail_route.container')
        self.assertEqual(routes[0][1], self.container.id)

    def test_sender_without_user_routes_as_the_processing_user(self):
        routes = self._route_email(
            self._build_email(
                to='sales@unknown.example.com',
                email_from='Nobody <nobody@unknown.example.com>',
            )
        )
        self.assertEqual(routes[0][3], self.env.uid)

    def test_sender_with_user_routes_as_that_user(self):
        user = mail_new_test_user(
            self.env,
            login='route_gateway_sender',
            email='gateway.sender@example.com',
            groups='base.group_user',
        )
        routes = self._route_email(
            self._build_email(
                to='sales@unknown.example.com',
                email_from='Sender <gateway.sender@example.com>',
            )
        )
        self.assertEqual(routes[0][3], user.id)

    def test_lost_mail_is_stored_on_the_container(self):
        subject = 'Wo ist meine Bestellung? 订单'
        raw = self._build_email(
            to='sales@unknown.example.com',
            subject=Header(subject, 'utf-8').encode(),
        )
        record_id = self.env['mail.thread'].message_process(False, raw)
        self.assertEqual(record_id, self.container.id)
        message = self.env['mail.message'].search(
            [('message_id', '=', '<route-1@example.com>')]
        )
        self.assertEqual(len(message), 1)
        self.assertEqual(message.model, 'muk_mail_route.container')
        self.assertEqual(message.res_id, self.container.id)
        self.assertEqual(message.subject, subject)
        self.assertEqual(message.email_from, '"John Doe" <john.doe@example.com>')

    def test_lost_mail_keeps_its_attachments(self):
        raw = self._build_email(
            to='sales@unknown.example.com',
            template=MAIL_TEMPLATE_ATTACHMENT,
        )
        self.env['mail.thread'].message_process(False, raw)
        message = self.env['mail.message'].search(
            [('message_id', '=', '<route-1@example.com>')]
        )
        self.assertEqual(message.attachment_ids.mapped('name'), ['invoice.txt'])
        self.assertEqual(message.attachment_ids.res_model, 'muk_mail_route.container')
        self.assertEqual(message.attachment_ids.res_id, self.container.id)
        self.assertEqual(message.attachment_ids.raw, b'Invoice content')

    def test_several_lost_mails_share_one_container(self):
        for index in range(2):
            self.env['mail.thread'].message_process(
                False,
                self._build_email(
                    to='sales@unknown.example.com',
                    msg_id=f'<route-{index}@example.com>',
                ),
            )
        containers = self.env['muk_mail_route.container'].search([])
        self.assertEqual(containers, self.container)
        self.assertEqual(
            self.env['mail.message'].search_count(
                [
                    ('model', '=', 'muk_mail_route.container'),
                    ('res_id', '=', self.container.id),
                ]
            ),
            2,
        )
