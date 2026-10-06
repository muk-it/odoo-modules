from __future__ import annotations

import datetime
from urllib.parse import parse_qs, urlparse

from freezegun import freeze_time

from odoo.tests import HttpCase, new_test_user
from odoo.tests.common import JsonRpcException
from odoo.tools import mute_logger


class TestOffice(HttpCase):
    """Test the Office Online viewer links."""

    @classmethod
    def setUpClass(cls) -> None:
        """Create an employee, an attachment they can read and one they cannot."""
        super().setUpClass()
        cls.user = new_test_user(
            cls.env, login='preview_office', groups='base.group_user'
        )
        cls.document = cls.env['ir.attachment'].create(
            {
                'name': 'offer.docx',
                'raw': b'PK-docx-content',
                'res_model': 'res.partner',
                'res_id': cls.user.partner_id.id,
            }
        )
        cls.private = cls.env['ir.attachment'].create(
            {
                'name': 'secret.docx',
                'raw': b'PK-secret',
            }
        )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _session_info(self) -> dict:
        """Return the session info the web client receives as the test user."""
        self.authenticate(self.user.login, self.user.login)
        return self.make_jsonrpc_request('/web/session/get_session_info')

    def _viewer_url(self, attachment_id: int) -> str:
        """Ask the server for the viewer URL of an attachment as the test user."""
        self.authenticate(self.user.login, self.user.login)
        return self.make_jsonrpc_request(f'/web_preview/office/{attachment_id}')

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_viewer_url(self):
        self.env['ir.config_parameter'].sudo().set_bool(
            'muk_web_preview.office_enabled', True
        )
        self.assertTrue(self._session_info()['preview_office_enabled'])
        viewer_url = urlparse(self._viewer_url(self.document.id))
        self.assertEqual(viewer_url.netloc, 'view.officeapps.live.com')
        file_url = urlparse(parse_qs(viewer_url.query)['src'][0])
        self.authenticate(None, None)
        response = self.url_open(file_url.path)
        self.assertEqual(response.content, b'PK-docx-content')
        with (
            freeze_time(datetime.datetime.now() + datetime.timedelta(minutes=6)),
            mute_logger('odoo.http'),
        ):
            self.assertEqual(self.url_open(file_url.path).status_code, 404)
        with mute_logger('odoo.http'):
            self.assertEqual(self.url_open(f'{file_url.path}x').status_code, 404)
            self.assertEqual(
                self.url_open('/web_preview/office/file/garbage').status_code, 404
            )

    def test_refused(self):
        self.env['ir.config_parameter'].sudo().set_bool(
            'muk_web_preview.office_enabled', False
        )
        self.assertFalse(self._session_info()['preview_office_enabled'])
        cases = [
            (False, self.document, 'werkzeug.exceptions.NotFound'),
            (True, self.private, 'odoo.exceptions.AccessError'),
        ]
        for enabled, attachment, error in cases:
            self.env['ir.config_parameter'].sudo().set_bool(
                'muk_web_preview.office_enabled', enabled
            )
            with self.subTest(error=error), mute_logger('odoo.http'):
                with self.assertRaises(JsonRpcException) as context:
                    self._viewer_url(attachment.id)
                self.assertEqual(context.exception.args[0], error)
