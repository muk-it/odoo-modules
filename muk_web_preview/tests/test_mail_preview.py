import base64
import email.mime.multipart
import email.mime.text

import odoo.tests

from odoo.tests.common import new_test_user, tagged


@tagged('post_install', '-at_install')
class TestMailPreview(odoo.tests.HttpCase):

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.test_user = new_test_user(
            cls.env,
            login='preview_test_user',
            password='preview_test_user',
            groups='base.group_user',
            context={
                'mail_create_nosubscribe': True,
                'mail_notrack': True,
                'no_reset_password': True,
            },
        )
        msg = email.mime.multipart.MIMEMultipart()
        msg['Subject'] = 'Test Email'
        msg['From'] = 'sender@example.com'
        msg['To'] = 'recipient@example.com'
        msg.attach(email.mime.text.MIMEText(
            '<html><body><p>Hello World</p></body></html>', 'html',
        ))
        cls.eml_attachment = cls.env['ir.attachment'].create({
            'name': 'test_email.eml',
            'raw': msg.as_bytes(),
            'mimetype': 'message/rfc822',
        })

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_mail_preview_returns_html(self):
        self.authenticate(self.test_user.login, 'preview_test_user')
        response = self.url_open(
            f'/muk_web_preview/preview/mail/{self.eml_attachment.id}',
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('Hello World', response.text)

    def test_mail_preview_unauthenticated(self):
        response = self.url_open(
            f'/muk_web_preview/preview/mail/{self.eml_attachment.id}',
        )
        self.assertNotEqual(response.status_code, 200)
