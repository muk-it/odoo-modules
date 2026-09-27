import json
from uuid import uuid4

from odoo.tests import HttpCase


class TestIrHttp(HttpCase):
    """Test the pager auto-load interval exposed in the session info."""

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_the_session_carries_the_configured_interval(self):
        self.authenticate('admin', 'admin')
        for configured, expected in [(None, 30000), (5000, 5000)]:
            with self.subTest(configured=configured):
                self.env['ir.config_parameter'].sudo().set_int(
                    'muk_web_refresh.pager_autoload_interval', configured
                )
                response = self.url_open(
                    '/web/session/get_session_info',
                    data=json.dumps(
                        {'jsonrpc': '2.0', 'method': 'call', 'id': str(uuid4())}
                    ),
                    headers={'Content-Type': 'application/json'},
                )
                result = response.json()['result']
                self.assertEqual(result['pager_autoload_interval'], expected)
