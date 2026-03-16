import json

from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestMcpController(HttpCase):

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _mcp_request(self, data, headers=None):
        all_headers = {
            'Content-Type': 'application/json',
        }
        if headers:
            all_headers.update(headers)
        return self.url_open(
            '/mcp',
            data=json.dumps(data),
            headers=all_headers,
        )

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_mcp_post_without_auth_is_rejected(self):
        response = self._mcp_request({
            'jsonrpc': '2.0',
            'id': 1,
            'method': 'initialize',
            'params': {},
        })
        self.assertNotEqual(response.status_code, 200)

    def test_mcp_get_without_auth_is_rejected(self):
        response = self.url_open('/mcp', headers={
            'Accept': 'text/event-stream',
        })
        self.assertNotEqual(response.status_code, 200)
