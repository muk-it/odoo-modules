from __future__ import annotations

import json
from uuid import uuid4

from odoo.tests import common
from odoo.tests.common import tagged


@tagged('post_install', '-at_install')
class TestIrHttp(common.HttpCase):
    """Test the pager auto-load interval exposed in the session info."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.user_password = 'refresh_session_user'
        cls.user = common.new_test_user(
            cls.env,
            'refresh_session_user',
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

    def _interval(self) -> int:
        """Authenticate and read the pager auto-load interval from the session."""
        self.authenticate(self.user.login, self.user_password)
        response = self.url_open(
            '/web/session/get_session_info',
            data=json.dumps({'jsonrpc': '2.0', 'method': 'call', 'id': str(uuid4())}),
            headers={'Content-Type': 'application/json'},
        )
        self.assertEqual(response.status_code, 200)
        return response.json()['result']['pager_autoload_interval']

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_the_interval_defaults_to_thirty_seconds(self):
        parameter = (
            self.env['ir.config_parameter']
            .sudo()
            .search([('key', '=', 'muk_web_refresh.pager_autoload_interval')])
        )
        parameter.unlink()
        self.assertEqual(self._interval(), 30000)

    def test_the_interval_follows_the_config_parameter(self):
        self.env['ir.config_parameter'].sudo().set_param(
            'muk_web_refresh.pager_autoload_interval', '5000'
        )
        interval = self._interval()
        self.assertEqual(interval, 5000)
        self.assertIsInstance(interval, int)
