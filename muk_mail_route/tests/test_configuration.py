from __future__ import annotations

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import tagged

from odoo.addons.mail.tests.common import MailCommon


@tagged('post_install', '-at_install')
class TestConfiguration(MailCommon):
    """Test the routing rule code validation and its default snippet."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.model_res_partner = cls.env.ref('base.model_res_partner')
        cls.container = cls.env['mail.thread']._get_failed_route_container()

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_forbidden_code_is_rejected(self):
        with self.assertRaises(ValidationError):
            self.env['muk_mail_route.configuration'].create(
                {
                    'name': 'Importing Rule',
                    'model_id': self.model_res_partner.id,
                    'code': 'import os\nvalues = {}',
                }
            )

    def test_code_with_a_syntax_error_is_rejected(self):
        with self.assertRaises(ValidationError):
            self.env['muk_mail_route.configuration'].create(
                {
                    'name': 'Broken Rule',
                    'model_id': self.model_res_partner.id,
                    'code': 'values = {',
                }
            )

    def test_writing_forbidden_code_is_rejected(self):
        configuration = self.env['muk_mail_route.configuration'].create(
            {
                'name': 'Valid Rule',
                'model_id': self.model_res_partner.id,
                'code': 'values = {}',
            }
        )
        with self.assertRaises(ValidationError):
            configuration.write({'code': 'import sys\nvalues = {}'})

    def test_default_code_builds_the_record_from_the_message(self):
        configuration = self.env['muk_mail_route.configuration'].create(
            {
                'name': 'Default Snippet',
                'model_id': self.model_res_partner.id,
                'route_type': 'new',
            }
        )
        self.assertTrue(configuration.code)
        message = self.container.message_post(
            subject='Anna Karenina',
            body='<p>Lost mail</p>',
            message_type='email',
            email_from='anna@example.com',
        )
        wizard = self.env['muk_mail_route.router'].create(
            {
                'configuration_id': configuration.id,
                'message_ids': [fields.Command.set(message.ids)],
            }
        )
        action = wizard.action_route()
        partner = self.env['res.partner'].search(action['domain'])
        self.assertEqual(partner.name, 'Anna Karenina')
        self.assertEqual(partner.email, 'anna@example.com')
