import base64
import ipaddress
import json
import socket
from unittest.mock import MagicMock, patch

from odoo.exceptions import UserError
from odoo.tests import common

from odoo.addons.muk_mcp.tools import url_fetch

PNG = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGA'
    'hKmMIQAAAABJRU5ErkJggg=='
)


class FakeResponse:

    def __init__(self, status, body=b'', headers=None):
        self.status = status
        self.headers = headers or {}
        self.body = body

    def stream(self, _chunk_size):
        yield self.body

    def release_conn(self):
        pass


class TestUrlFetch(common.TransactionCase):

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tool_model = cls.env['muk_mcp.tool']
        cls.partner = cls.env['res.partner'].create({'name': 'MCP Image'})

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _call(self, name, arguments):
        text, _info = self.tool_model._call(name, arguments, self.env)
        return json.loads(text)

    @staticmethod
    def _getaddrinfo(host, *_args, **_kwargs):
        try:
            address = str(ipaddress.ip_address(host))
        except ValueError:
            address = '93.184.216.34'
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', (address, 0))]

    def _mock_network(self, *responses):
        pool = MagicMock()
        pool.return_value.urlopen.side_effect = list(responses)
        for patcher in (
            patch.object(
                url_fetch.socket, 'getaddrinfo', side_effect=self._getaddrinfo
            ),
            patch.object(url_fetch.urllib3, 'HTTPSConnectionPool', pool),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        return pool

    def _set_image(self, url):
        return self._call('set_binary_from_url', {
            'model': 'res.partner',
            'id': self.partner.id,
            'field': 'image_1920',
            'url': url,
        })

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_set_binary_from_url(self):
        pool = self._mock_network(FakeResponse(
            200, PNG, {'Content-Type': 'image/png'}
        ))
        result = self._set_image('http://example.com/image.png')
        self.assertEqual(result, {
            'success': True,
            'id': self.partner.id,
            'field': 'image_1920',
            'size': len(PNG),
            'mimetype': 'image/png',
        })
        self.assertTrue(self.partner.image_1920)
        pool.assert_called_once()
        self.assertEqual(pool.call_args.kwargs['host'], '93.184.216.34')
        self.assertEqual(pool.call_args.kwargs['server_hostname'], 'example.com')

    def test_rejects_private_address(self):
        for url in (
            'https://127.0.0.1/image.png',
            'https://10.0.0.1/image.png',
            'https://169.254.169.254/latest/meta-data',
        ):
            with self.assertRaisesRegex(UserError, 'not publicly routable'):
                self._set_image(url)
        self.assertFalse(self.partner.image_1920)

    def test_rejects_redirect_to_private_address(self):
        pool = self._mock_network(FakeResponse(
            302, headers={'Location': 'https://192.168.0.1/image.png'}
        ))
        with self.assertRaisesRegex(UserError, 'not publicly routable'):
            self._set_image('https://example.com/image.png')
        pool.assert_called_once()

    def test_rejects_non_https_scheme(self):
        with self.assertRaisesRegex(UserError, 'https'):
            self._set_image('file:///etc/passwd')

    def test_rejects_oversized_body(self):
        self._mock_network(FakeResponse(200, PNG))
        with self.assertRaisesRegex(UserError, 'exceeds'):
            url_fetch.fetch_url('https://example.com/image.png', max_bytes=10)

    def test_rejects_non_image_content(self):
        self._mock_network(FakeResponse(
            200, b'<html><body>Not found</body></html>',
            {'Content-Type': 'text/html'},
        ))
        with self.assertRaisesRegex(UserError, 'not an image'):
            self._set_image('https://example.com/image.png')
        self.assertFalse(self.partner.image_1920)

    def test_rejects_non_binary_field(self):
        with self.assertRaisesRegex(UserError, 'not a binary field'):
            self._call('set_binary_from_url', {
                'model': 'res.partner',
                'id': self.partner.id,
                'field': 'name',
                'url': 'https://example.com/image.png',
            })

    def test_rejects_missing_record(self):
        with self.assertRaisesRegex(UserError, 'does not exist'):
            self._call('set_binary_from_url', {
                'model': 'res.partner',
                'id': 999999999,
                'field': 'image_1920',
                'url': 'https://example.com/image.png',
            })
