from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time

from requests import Response

import odoo.tests
from odoo.tests.common import new_test_user, tagged
from odoo.tools import mute_logger


@tagged('post_install', '-at_install')
class TestOfficePreview(odoo.tests.HttpCase):
    """Test the Office preview token and file serving controller."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
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
        cls.docx_attachment = cls.env['ir.attachment'].create(
            {
                'name': 'test_doc.docx',
                'raw': b'PK\x03\x04fake_docx_content',
                'mimetype': (
                    'application/vnd.openxmlformats-officedocument'
                    '.wordprocessingml.document'
                ),
                'public': True,
            }
        )
        cls.other_attachment = cls.env['ir.attachment'].create(
            {
                'name': 'other_doc.docx',
                'raw': b'PK\x03\x04other_content',
                'mimetype': (
                    'application/vnd.openxmlformats-officedocument'
                    '.wordprocessingml.document'
                ),
                'public': True,
            }
        )
        parameter = cls.env['ir.config_parameter'].sudo().search([], limit=1)
        cls.restricted_attachment = cls.env['ir.attachment'].create(
            {
                'name': 'restricted.docx',
                'raw': b'PK\x03\x04restricted',
                'res_model': 'ir.config_parameter',
                'res_id': parameter.id,
            }
        )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @classmethod
    def _sign(cls, payload: str) -> str:
        """Return the HMAC signature of a token payload."""
        secret = cls.env['ir.config_parameter'].sudo().get_param('database.secret')
        return hmac.new(
            secret.encode(),
            payload.encode(),
            hashlib.sha256,
        ).hexdigest()

    @classmethod
    def _make_token(cls, attachment_id: int, ttl: int = 300) -> str:
        """Build a signed access token for an attachment id."""
        payload = f'{attachment_id}:{int(time.time()) + ttl}:{secrets.token_hex(16)}'
        return f'{payload}:{cls._sign(payload)}'

    def _request_token(self, attachment_id: int) -> Response:
        """Call the Office token endpoint for an attachment id."""
        return self.url_open(
            '/muk_web_preview/office/token',
            data=json.dumps(
                {
                    'jsonrpc': '2.0',
                    'method': 'call',
                    'params': {'attachment_id': attachment_id},
                }
            ),
            headers={'Content-Type': 'application/json'},
        )

    def _fetch_file(self, attachment_id: int, token: str | None) -> Response:
        """Request the Office file endpoint with an optional token."""
        url = f'/muk_web_preview/office/file/{attachment_id}'
        if token is not None:
            url = f'{url}?token={token}'
        return self.url_open(url, allow_redirects=False)

    def _enable_office(self, enabled: bool) -> None:
        """Toggle the Office preview configuration parameter."""
        self.env['ir.config_parameter'].sudo().set_param(
            'muk_web_preview.office_enabled',
            'True' if enabled else 'False',
        )

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_office_token_disabled(self):
        self._enable_office(False)
        self.authenticate(self.test_user.login, 'office_preview_test_user')
        result = self._request_token(self.docx_attachment.id).json()['result']
        self.assertEqual(result, {'error': 'Office preview is disabled'})

    def test_office_token_enabled(self):
        self._enable_office(True)
        self.authenticate(self.test_user.login, 'office_preview_test_user')
        result = self._request_token(self.docx_attachment.id).json()['result']
        self.assertIn('viewer_url', result)
        self.assertIn('view.officeapps.live.com', result['viewer_url'])
        self.assertIn(
            f'/muk_web_preview/office/file/{self.docx_attachment.id}',
            result['viewer_url'],
        )
        self.assertIn('token=', result['viewer_url'])

    def test_office_token_requires_authentication(self):
        self._enable_office(True)
        response = self._request_token(self.docx_attachment.id)
        self.assertIn('error', response.json())

    @mute_logger('odoo.http')
    def test_office_token_requires_read_access(self):
        self._enable_office(True)
        self.authenticate(self.test_user.login, 'office_preview_test_user')
        payload = self._request_token(self.restricted_attachment.id).json()
        self.assertIn('error', payload)
        self.assertNotIn('result', payload)

    def test_office_file_valid_token_serves_the_content(self):
        self._enable_office(True)
        response = self._fetch_file(
            self.docx_attachment.id,
            self._make_token(self.docx_attachment.id),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b'PK\x03\x04fake_docx_content')

    def test_office_file_serves_without_a_session(self):
        self._enable_office(True)
        self.opener.cookies.clear()
        response = self._fetch_file(
            self.docx_attachment.id,
            self._make_token(self.docx_attachment.id),
        )
        self.assertEqual(response.status_code, 200)

    def test_office_file_missing_token(self):
        response = self._fetch_file(self.docx_attachment.id, None)
        self.assertEqual(response.status_code, 404)

    def test_office_file_invalid_token(self):
        response = self._fetch_file(self.docx_attachment.id, 'invalid')
        self.assertEqual(response.status_code, 404)

    def test_office_file_non_numeric_token_fields(self):
        payload = f'abc:xyz:{secrets.token_hex(16)}'
        response = self._fetch_file(
            self.docx_attachment.id,
            f'{payload}:{self._sign(payload)}',
        )
        self.assertEqual(response.status_code, 404)

    def test_office_file_expired_token(self):
        response = self._fetch_file(
            self.docx_attachment.id,
            self._make_token(self.docx_attachment.id, ttl=-1),
        )
        self.assertEqual(response.status_code, 404)

    def test_office_file_token_bound_to_another_attachment(self):
        response = self._fetch_file(
            self.docx_attachment.id,
            self._make_token(self.other_attachment.id),
        )
        self.assertEqual(response.status_code, 404)

    def test_office_file_tampered_signature(self):
        token = self._make_token(self.docx_attachment.id)
        payload, signature = token.rsplit(':', 1)
        flipped = ('0' if signature[0] != '0' else '1') + signature[1:]
        response = self._fetch_file(self.docx_attachment.id, f'{payload}:{flipped}')
        self.assertEqual(response.status_code, 404)

    def test_office_file_tampered_expiry(self):
        token = self._make_token(self.docx_attachment.id)
        attachment_id, _expires, nonce, signature = token.split(':')
        forged = f'{attachment_id}:{int(time.time()) + 86400}:{nonce}:{signature}'
        response = self._fetch_file(self.docx_attachment.id, forged)
        self.assertEqual(response.status_code, 404)

    def test_office_file_unknown_attachment(self):
        missing_id = self.env['ir.attachment'].search([], order='id desc', limit=1).id
        missing_id += 1000
        response = self._fetch_file(missing_id, self._make_token(missing_id))
        self.assertEqual(response.status_code, 404)
