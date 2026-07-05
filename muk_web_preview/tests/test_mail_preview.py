from __future__ import annotations

import email.mime.image
import email.mime.multipart
import email.mime.text

import odoo.tests
from odoo import models
from odoo.tests.common import new_test_user, tagged


@tagged('post_install', '-at_install')
class TestMailPreview(odoo.tests.HttpCase):
    """Test the RFC 822 email attachment preview controller."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
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
        cls.eml_html = cls._create_html_eml()
        cls.eml_plain = cls._create_plain_eml()
        cls.eml_cid = cls._create_cid_eml()
        cls.eml_attachment = cls._create_attachment_eml()
        cls.eml_bad_charset = cls._create_bad_charset_eml()
        cls.env['ir.model.data'].create(
            {
                'name': 'test_mail_preview_html_eml',
                'module': 'muk_web_preview',
                'model': 'ir.attachment',
                'res_id': cls.eml_html.id,
            }
        )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @classmethod
    def _create_html_eml(cls) -> models.BaseModel:
        """Create an HTML email attachment with common headers."""
        msg = email.mime.multipart.MIMEMultipart()
        msg['Subject'] = 'Test HTML Email'
        msg['From'] = 'sender@example.com'
        msg['To'] = 'recipient@example.com'
        msg['Cc'] = 'cc@example.com'
        msg.attach(
            email.mime.text.MIMEText(
                '<html><body><p>Hello World</p></body></html>',
                'html',
            )
        )
        return cls.env['ir.attachment'].create(
            {
                'name': 'html_email.eml',
                'raw': msg.as_bytes(),
                'mimetype': 'message/rfc822',
                'public': True,
            }
        )

    @classmethod
    def _create_plain_eml(cls) -> models.BaseModel:
        """Create a plain text email attachment."""
        msg = email.mime.text.MIMEText(
            'This is plain text content.\nLine two.',
            'plain',
        )
        msg['Subject'] = 'Plain Text Email'
        msg['From'] = 'plain@example.com'
        msg['To'] = 'recipient@example.com'
        return cls.env['ir.attachment'].create(
            {
                'name': 'plain_email.eml',
                'raw': msg.as_bytes(),
                'mimetype': 'message/rfc822',
                'public': True,
            }
        )

    @classmethod
    def _create_cid_eml(cls) -> models.BaseModel:
        """Create an HTML email attachment referencing an inline CID image."""
        msg = email.mime.multipart.MIMEMultipart('related')
        msg['Subject'] = 'Email with CID Image'
        msg['From'] = 'images@example.com'
        msg['To'] = 'recipient@example.com'
        html = email.mime.text.MIMEText(
            '<html><body><img src="cid:test123"/></body></html>',
            'html',
        )
        msg.attach(html)
        pixel = (
            b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01'
            b'\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00'
            b'\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00'
            b'\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82'
        )
        img = email.mime.image.MIMEImage(pixel, 'png')
        img.add_header('Content-ID', '<test123>')
        img.add_header('Content-Disposition', 'inline', filename='pixel.png')
        msg.attach(img)
        return cls.env['ir.attachment'].create(
            {
                'name': 'cid_email.eml',
                'raw': msg.as_bytes(),
                'mimetype': 'message/rfc822',
                'public': True,
            }
        )

    @classmethod
    def _create_attachment_eml(cls) -> models.BaseModel:
        """Create an HTML email attachment carrying a file attachment."""
        msg = email.mime.multipart.MIMEMultipart('mixed')
        msg['Subject'] = 'Email with Attachment'
        msg['From'] = 'attach@example.com'
        msg['To'] = 'recipient@example.com'
        msg.attach(
            email.mime.text.MIMEText(
                '<html><body><p>See attached.</p></body></html>',
                'html',
            )
        )
        att = email.mime.text.MIMEText('col1,col2\na,b\n', 'csv')
        att.add_header(
            'Content-Disposition',
            'attachment',
            filename='data.csv',
        )
        msg.attach(att)
        return cls.env['ir.attachment'].create(
            {
                'name': 'attachment_email.eml',
                'raw': msg.as_bytes(),
                'mimetype': 'message/rfc822',
                'public': True,
            }
        )

    @classmethod
    def _create_bad_charset_eml(cls) -> models.BaseModel:
        """Create an HTML email attachment declaring an unknown charset."""
        raw = (
            b'From: sender@example.com\r\n'
            b'To: recipient@example.com\r\n'
            b'Subject: Bad Charset Email\r\n'
            b'MIME-Version: 1.0\r\n'
            b'Content-Type: text/html; charset="bogus-charset-xyz"\r\n'
            b'Content-Transfer-Encoding: 7bit\r\n'
            b'\r\n'
            b'<p>hello bad charset</p>\r\n'
        )
        return cls.env['ir.attachment'].create(
            {
                'name': 'bad_charset_email.eml',
                'raw': raw,
                'mimetype': 'message/rfc822',
                'public': True,
            }
        )

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def _preview(self, attachment: models.BaseModel):
        """Authenticate and request the mail preview for an attachment."""
        self.authenticate(self.test_user.login, 'preview_test_user')
        return self.url_open(
            f'/muk_web_preview/preview/mail/{attachment.id}',
        )

    def test_html_body(self):
        response = self._preview(self.eml_html)
        self.assertEqual(response.status_code, 200)
        self.assertIn('Hello World', response.text)

    def test_html_headers_rendered(self):
        response = self._preview(self.eml_html)
        self.assertIn('sender@example.com', response.text)
        self.assertIn('recipient@example.com', response.text)
        self.assertIn('cc@example.com', response.text)
        self.assertIn('Test HTML Email', response.text)
        self.assertIn('muk_mail_header', response.text)

    def test_html_structure(self):
        response = self._preview(self.eml_html)
        self.assertIn('<!DOCTYPE html>', response.text)
        self.assertIn('muk_mail_body', response.text)

    def test_plain_text_body(self):
        response = self._preview(self.eml_plain)
        self.assertEqual(response.status_code, 200)
        self.assertIn('This is plain text content.', response.text)
        self.assertIn('<pre>', response.text)

    def test_plain_text_headers(self):
        response = self._preview(self.eml_plain)
        self.assertIn('Plain Text Email', response.text)
        self.assertIn('plain@example.com', response.text)

    def test_cid_image_resolved(self):
        response = self._preview(self.eml_cid)
        self.assertEqual(response.status_code, 200)
        self.assertIn('data:image/png;base64,', response.text)
        self.assertNotIn('cid:test123', response.text)

    def test_cid_image_headers(self):
        response = self._preview(self.eml_cid)
        self.assertIn('images@example.com', response.text)
        self.assertIn('Email with CID Image', response.text)

    def test_file_attachment_listed(self):
        response = self._preview(self.eml_attachment)
        self.assertEqual(response.status_code, 200)
        self.assertIn('data.csv', response.text)
        self.assertIn('muk_mail_attachments', response.text)
        self.assertIn('Attachments:', response.text)

    def test_file_attachment_body(self):
        response = self._preview(self.eml_attachment)
        self.assertIn('See attached.', response.text)

    def test_bad_charset_body_does_not_crash(self):
        response = self._preview(self.eml_bad_charset)
        self.assertEqual(response.status_code, 200)
        self.assertIn('muk_mail_body', response.text)
        self.assertIn('hello bad charset', response.text)

    def test_xmlid_route(self):
        self.authenticate(self.test_user.login, 'preview_test_user')
        response = self.url_open(
            '/muk_web_preview/preview/mail/muk_web_preview.test_mail_preview_html_eml',
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('Hello World', response.text)
        self.assertIn('muk_mail_body', response.text)

    def test_unauthenticated(self):
        response = self.url_open(
            f'/muk_web_preview/preview/mail/{self.eml_html.id}',
            allow_redirects=False,
        )
        self.assertIn(response.status_code, (303, 403))
