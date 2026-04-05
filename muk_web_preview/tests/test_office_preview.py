import hashlib
import hmac
import json
import secrets

import odoo.tests

from odoo.tests.common import new_test_user
from odoo.tests.common import tagged


@tagged('post_install', '-at_install')
class TestOfficePreview(odoo.tests.HttpCase):

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.test_user = new_test_user(
            cls.env,
            login='office_preview_test_user',
            password='office_preview_test_user',
            groups='base.group_user',
            context={
                'mail_create_nosubscribe': True,
                'mail_notrack': True,
                'no_reset_password': True,
            },
        )
        cls.docx_attachment = cls.env['ir.attachment'].create({
            'name': 'test_doc.docx',
            'raw': b'PK\x03\x04fake_docx_content',
            'mimetype': (
                'application/vnd.openxmlformats-officedocument'
                '.wordprocessingml.document'
            ),
            'public': True,
        })

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_office_token_disabled(self):
        self.env['ir.config_parameter'].sudo().set_param(
            'muk_web_preview.office_enabled', 'False',
        )
        self.authenticate(self.test_user.login, 'office_preview_test_user')
        response = self.url_open(
            '/muk_web_preview/office/token',
            data=json.dumps({
                'jsonrpc': '2.0',
                'method': 'call',
                'params': {
                    'attachment_id': self.docx_attachment.id,
                },
            }),
            headers={'Content-Type': 'application/json'},
        )
        result = response.json().get('result', {})
        self.assertIn('error', result)

    def test_office_token_enabled(self):
        self.env['ir.config_parameter'].sudo().set_param(
            'muk_web_preview.office_enabled', 'True',
        )
        self.authenticate(self.test_user.login, 'office_preview_test_user')
        response = self.url_open(
            '/muk_web_preview/office/token',
            data=json.dumps({
                'jsonrpc': '2.0',
                'method': 'call',
                'params': {
                    'attachment_id': self.docx_attachment.id,
                },
            }),
            headers={'Content-Type': 'application/json'},
        )
        result = response.json().get('result', {})
        self.assertIn('viewer_url', result)
        self.assertIn('view.officeapps.live.com', result['viewer_url'])

    def test_office_file_invalid_token(self):
        response = self.url_open(
            f'/muk_web_preview/office/file/{self.docx_attachment.id}'
            '?token=invalid',
            allow_redirects=False,
        )
        self.assertEqual(response.status_code, 404)

    def test_office_file_expired_token(self):
        secret = self.env['ir.config_parameter'].sudo().get_param(
            'database.secret',
        )
        expires = 0
        nonce = secrets.token_hex(16)
        payload = f'{self.docx_attachment.id}:{expires}:{nonce}'
        signature = hmac.new(
            secret.encode(), payload.encode(), hashlib.sha256,
        ).hexdigest()
        token = f'{payload}:{signature}'
        response = self.url_open(
            f'/muk_web_preview/office/file/{self.docx_attachment.id}'
            f'?token={token}',
            allow_redirects=False,
        )
        self.assertEqual(response.status_code, 404)
