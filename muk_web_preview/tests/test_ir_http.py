from __future__ import annotations

import json
from uuid import uuid4

from odoo.tests import common
from odoo.tests.common import tagged


@tagged('post_install', '-at_install')
class TestIrHttp(common.HttpCase):
    """Test the Office preview flag exposed in the session info."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.user_password = 'preview_session_user'
        cls.user = common.new_test_user(
            cls.env,
            'preview_session_user',
            password=cls.user_password,
            groups='base.group_user',
            context={
                'mail_create_nosubscribe': True,
                'mail_notrack': True,
                'no_reset_password': True,
            },
        )
        cls.env['res.users.settings']._find_or_create_for_user(cls.user)

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _session_info(self) -> dict:
        """Authenticate and return the parsed session info payload."""
        self.authenticate(self.user.login, self.user_password)
        response = self.url_open(
            '/web/session/get_session_info',
            data=json.dumps({'jsonrpc': '2.0', 'method': 'call', 'id': str(uuid4())}),
            headers={'Content-Type': 'application/json'},
        )
        self.assertEqual(response.status_code, 200)
        return response.json()['result']

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_office_flag_defaults_to_false(self):
        self.env['ir.config_parameter'].sudo().set_param(
            'muk_web_preview.office_enabled', ''
        )
        self.assertFalse(self._session_info()['preview_office_enabled'])

    def test_office_flag_follows_the_config_parameter(self):
        self.env['ir.config_parameter'].sudo().set_param(
            'muk_web_preview.office_enabled', 'True'
        )
        self.assertTrue(self._session_info()['preview_office_enabled'])

    def test_office_flag_ignores_a_malformed_config_parameter(self):
        self.env['ir.config_parameter'].sudo().set_param(
            'muk_web_preview.office_enabled', 'not-a-boolean'
        )
        self.assertFalse(self._session_info()['preview_office_enabled'])

    def test_settings_toggle_writes_the_config_parameter(self):
        settings = self.env['res.config.settings'].create(
            {'preview_office_enabled': True}
        )
        settings.execute()
        self.assertTrue(self._session_info()['preview_office_enabled'])
        settings = self.env['res.config.settings'].create(
            {'preview_office_enabled': False}
        )
        settings.execute()
        self.assertFalse(self._session_info()['preview_office_enabled'])
