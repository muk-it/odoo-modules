from __future__ import annotations

from odoo.tests import tagged

from .common import MailRouteCommon


@tagged('post_install', '-at_install')
class TestRoutingAlias(MailRouteCommon):
    """Test that valid alias and reply routes are not hijacked by the fallback."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.container = cls.env['mail.thread']._get_failed_route_container()
        cls.partner = cls.env['res.partner'].create({'name': 'Alias Target'})
        cls.alias = cls.env['mail.alias'].create(
            {
                'alias_name': 'contactbox',
                'alias_model_id': cls.env.ref('base.model_res_partner').id,
            }
        )
        cls.alias_email = f'contactbox@{cls.alias_domain}'

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_alias_match_wins_over_the_container(self):
        routes = self._route_email(self._build_email(to=self.alias_email))
        self.assertEqual(len(routes), 1)
        model, thread_id, _values, _user_id, alias = routes[0]
        self.assertEqual(model, 'res.partner')
        self.assertFalse(thread_id)
        self.assertEqual(alias, self.alias)

    def test_restricted_alias_falls_back_to_the_container(self):
        self.alias.write({'alias_contact': 'partners'})
        routes = self._route_email(
            self._build_email(
                to=self.alias_email,
                email_from='Stranger <stranger@unknown.example.com>',
            )
        )
        self.assertEqual(len(routes), 1)
        self.assertEqual(routes[0][0], 'muk_mail_route.container')
        self.assertEqual(routes[0][1], self.container.id)

    def test_reply_to_a_thread_wins_over_the_container(self):
        message = self.partner.message_post(
            body='<p>Initial</p>',
            subject='Initial',
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
        )
        routes = self._route_email(
            self._build_email(
                to='sales@unknown.example.com',
                extra=f'References: {message.message_id}',
            )
        )
        self.assertEqual(len(routes), 1)
        self.assertEqual(routes[0][0], 'res.partner')
        self.assertEqual(routes[0][1], self.partner.id)

    def test_reply_to_a_lost_mail_stays_in_the_container(self):
        message = self.container.message_post(
            body='<p>Lost</p>',
            subject='Lost',
            message_type='email',
        )
        routes = self._route_email(
            self._build_email(
                to='sales@unknown.example.com',
                extra=f'In-Reply-To: {message.message_id}',
            )
        )
        self.assertEqual(len(routes), 1)
        self.assertEqual(routes[0][0], 'muk_mail_route.container')
        self.assertEqual(routes[0][1], self.container.id)

    def test_reply_to_a_deleted_thread_falls_back_to_the_container(self):
        message = self.partner.message_post(
            body='<p>Initial</p>',
            subject='Initial',
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
        )
        message_id = message.message_id
        self.partner.unlink()
        routes = self._route_email(
            self._build_email(
                to='sales@unknown.example.com',
                extra=f'References: {message_id}',
            )
        )
        self.assertEqual(len(routes), 1)
        self.assertEqual(routes[0][0], 'muk_mail_route.container')
        self.assertEqual(routes[0][1], self.container.id)
