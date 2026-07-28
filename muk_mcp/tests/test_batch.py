from odoo.tests import tagged

from odoo.addons.muk_mcp.tests.common import MCPHttpCase


@tagged('post_install', '-at_install')
class TestBatch(MCPHttpCase):
    """Verify JSON-RPC batching is refused on every served revision."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.session_model = cls.env['muk_mcp.session']

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_batch_is_rejected(self):
        response = self.mcp_post([self.mcp_ping(1), self.mcp_ping(2)])
        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertIsInstance(body, dict)
        self.assertEqual(body['error']['code'], -32600)
        self.assertIn('batching is not supported', body['error']['message'])

    def test_empty_batch_is_rejected(self):
        response = self.mcp_post([])
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error']['code'], -32600)

    def test_batch_never_creates_a_session(self):
        before = self.session_model.search_count([])
        self.mcp_post(
            [{'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
              'params': {}}],
        )
        self.assertEqual(self.session_model.search_count([]), before)

    def test_array_params_are_a_clean_invalid_request(self):
        response = self.mcp_post(
            {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list',
             'params': [1]},
        )
        self.assertEqual(response.status_code, 400)
        error = response.json()['error']
        self.assertEqual(error['code'], -32600)
        self.assertIn('params', error['message'])
        self.assertNotIn('Traceback', response.text)
