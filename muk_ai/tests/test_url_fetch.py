from __future__ import annotations

import base64
import socket
from unittest.mock import MagicMock, patch

import urllib3

from odoo.exceptions import UserError

from odoo.addons.muk_ai.tests.common import AITestCommon
from odoo.addons.muk_ai.tools.url_fetch import (
    CONNECT_TIMEOUT,
    READ_TIMEOUT,
    _validate_url,
    fetch_url,
)

PNG_1x1_RED = base64.b64encode(
    bytes.fromhex(
        '89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4'
        '890000000d49444154789c63f8cf00000003000100184b96c10000000049454e'
        '44ae426082'
    )
).decode()


class TestUrlFetchHardening(AITestCommon):
    """Verify SSRF guards and size caps for the @url fetch helper."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    def setUp(self) -> None:
        super().setUp()
        self.session = (
            self.env['muk_ai.session']
            .sudo()
            .create(
                {
                    'name': 'url-fetch-test',
                    'user_id': self.env.user.id,
                }
            )
        )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @staticmethod
    def _addrinfo(ip: str) -> list[tuple]:
        """Build a ``socket.getaddrinfo`` result resolving to a single IP."""
        return [(0, 0, 0, '', (ip, 0))]

    def _mock_response(
        self,
        chunks: list[bytes],
        status: int = 200,
        headers: dict | None = None,
    ) -> MagicMock:
        """Build a mocked urllib3 response streaming the given body chunks."""
        response = MagicMock()
        response.status = status
        response.headers = headers if headers is not None else {}
        response.stream.return_value = iter(chunks)
        response.release_conn.return_value = None
        return response

    def _mock_pool(self, response: MagicMock) -> MagicMock:
        """Build a mocked connection pool whose ``urlopen`` returns ``response``."""
        pool = MagicMock()
        pool.urlopen.return_value = response
        pool.close.return_value = None
        return pool

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_https_only(self):
        url = 'http://example.com/cat.png'
        with patch(
            'odoo.addons.muk_ai.tools.url_fetch.urllib3.HTTPSConnectionPool',
        ) as mock_pool_cls:
            args = {'values': {'image_1920': f'@url:{url}'}}
            resolved, refs = self.session._resolve_value_refs(args)
        mock_pool_cls.assert_not_called()
        self.assertEqual(resolved['values']['image_1920'], f'@url:{url}')
        self.assertEqual(refs, [])

    def test_rejects_private_ip(self):
        url = 'https://internal.example.com/secret.png'
        with (
            patch(
                'odoo.addons.muk_ai.tools.url_fetch.socket.getaddrinfo',
                return_value=self._addrinfo('10.0.0.1'),
            ),
            patch(
                'odoo.addons.muk_ai.tools.url_fetch.urllib3.HTTPSConnectionPool',
            ) as mock_pool_cls,
        ):
            args = {'values': {'image_1920': f'@url:{url}'}}
            resolved, refs = self.session._resolve_value_refs(args)
        mock_pool_cls.assert_not_called()
        self.assertEqual(resolved['values']['image_1920'], f'@url:{url}')
        self.assertEqual(refs, [])

    def test_rejects_loopback(self):
        url = 'https://localhost/admin'
        with (
            patch(
                'odoo.addons.muk_ai.tools.url_fetch.socket.getaddrinfo',
                return_value=self._addrinfo('127.0.0.1'),
            ),
            patch(
                'odoo.addons.muk_ai.tools.url_fetch.urllib3.HTTPSConnectionPool',
            ) as mock_pool_cls,
        ):
            args = {'values': {'image_1920': f'@url:{url}'}}
            resolved, refs = self.session._resolve_value_refs(args)
        mock_pool_cls.assert_not_called()
        self.assertEqual(resolved['values']['image_1920'], f'@url:{url}')
        self.assertEqual(refs, [])

    def test_rejects_link_local(self):
        url = 'https://metadata.example/aws'
        with (
            patch(
                'odoo.addons.muk_ai.tools.url_fetch.socket.getaddrinfo',
                return_value=self._addrinfo('169.254.169.254'),
            ),
            patch(
                'odoo.addons.muk_ai.tools.url_fetch.urllib3.HTTPSConnectionPool',
            ) as mock_pool_cls,
        ):
            args = {'values': {'image_1920': f'@url:{url}'}}
            resolved, refs = self.session._resolve_value_refs(args)
        mock_pool_cls.assert_not_called()
        self.assertEqual(resolved['values']['image_1920'], f'@url:{url}')
        self.assertEqual(refs, [])

    def test_size_cap(self):
        url = 'https://example.com/huge.bin'
        big_chunk = b'x' * (1024 * 1024)
        chunks = [big_chunk] * 17
        response = self._mock_response(chunks)
        pool = self._mock_pool(response)
        with (
            patch(
                'odoo.addons.muk_ai.tools.url_fetch.socket.getaddrinfo',
                return_value=self._addrinfo('8.8.8.8'),
            ),
            patch(
                'odoo.addons.muk_ai.tools.url_fetch.urllib3.HTTPSConnectionPool',
                return_value=pool,
            ),
        ):
            args = {'values': {'image_1920': f'@url:{url}'}}
            resolved, refs = self.session._resolve_value_refs(args)
        self.assertEqual(resolved['values']['image_1920'], f'@url:{url}')
        self.assertEqual(refs, [])
        response.release_conn.assert_called()
        pool.close.assert_called()

    def test_no_redirects(self):
        url = 'https://example.com/cat.png'
        png = base64.b64decode(PNG_1x1_RED)
        response = self._mock_response([png])
        pool = self._mock_pool(response)
        with (
            patch(
                'odoo.addons.muk_ai.tools.url_fetch.socket.getaddrinfo',
                return_value=self._addrinfo('8.8.8.8'),
            ),
            patch(
                'odoo.addons.muk_ai.tools.url_fetch.urllib3.HTTPSConnectionPool',
                return_value=pool,
            ),
        ):
            args = {'values': {'image_1920': f'@url:{url}'}}
            self.session._resolve_value_refs(args)
        pool.urlopen.assert_called_once()
        kwargs = pool.urlopen.call_args.kwargs
        self.assertEqual(kwargs.get('redirect'), False)
        self.assertEqual(kwargs.get('preload_content'), False)

    def test_happy_path(self):
        url = 'https://example.com/cat.png'
        png = base64.b64decode(PNG_1x1_RED)
        response = self._mock_response([png[:8], png[8:]])
        pool = self._mock_pool(response)
        with (
            patch(
                'odoo.addons.muk_ai.tools.url_fetch.socket.getaddrinfo',
                return_value=self._addrinfo('8.8.8.8'),
            ),
            patch(
                'odoo.addons.muk_ai.tools.url_fetch.urllib3.HTTPSConnectionPool',
                return_value=pool,
            ) as mock_pool_cls,
        ):
            args = {'values': {'image_1920': f'@url:{url}'}}
            resolved, refs = self.session._resolve_value_refs(args)
        self.assertEqual(resolved['values']['image_1920'], PNG_1x1_RED)
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0]['kind'], 'url')
        self.assertEqual(refs[0]['preview_url'], url)
        mock_pool_cls.assert_called_once()
        pool_kwargs = mock_pool_cls.call_args.kwargs
        self.assertEqual(pool_kwargs.get('host'), '8.8.8.8')
        self.assertEqual(pool_kwargs.get('assert_hostname'), 'example.com')
        self.assertEqual(pool_kwargs.get('retries'), False)
        urlopen_kwargs = pool.urlopen.call_args.kwargs
        self.assertEqual(urlopen_kwargs.get('headers', {}).get('Host'), 'example.com')

    def test_dns_failure_swallowed(self):
        url = 'https://nonexistent.invalid/x.png'
        with patch(
            'odoo.addons.muk_ai.tools.url_fetch.socket.getaddrinfo',
            side_effect=socket.gaierror('name does not resolve'),
        ):
            args = {'values': {'image_1920': f'@url:{url}'}}
            resolved, refs = self.session._resolve_value_refs(args)
        self.assertEqual(resolved['values']['image_1920'], f'@url:{url}')
        self.assertEqual(refs, [])

    def test_validate_url_returns_pinned_ips(self):
        with patch(
            'odoo.addons.muk_ai.tools.url_fetch.socket.getaddrinfo',
            return_value=self._addrinfo('8.8.8.8'),
        ):
            host, ips = _validate_url('https://example.com/x.png')
        self.assertEqual(host, 'example.com')
        self.assertEqual(ips, ['8.8.8.8'])

    def test_pool_pinned_to_validated_ip(self):
        url = 'https://rebind.example/payload.png'
        png = base64.b64decode(PNG_1x1_RED)
        response = self._mock_response([png])
        pool = self._mock_pool(response)
        with (
            patch(
                'odoo.addons.muk_ai.tools.url_fetch.socket.getaddrinfo',
                return_value=self._addrinfo('8.8.8.8'),
            ),
            patch(
                'odoo.addons.muk_ai.tools.url_fetch.urllib3.HTTPSConnectionPool',
                return_value=pool,
            ) as mock_pool_cls,
        ):
            args = {'values': {'image_1920': f'@url:{url}'}}
            self.session._resolve_value_refs(args)
        kwargs = mock_pool_cls.call_args.kwargs
        self.assertEqual(kwargs.get('host'), '8.8.8.8')
        self.assertEqual(kwargs.get('assert_hostname'), 'rebind.example')
        self.assertEqual(kwargs.get('server_hostname'), 'rebind.example')

    def test_follows_redirect_and_revalidates_each_hop(self):
        png = base64.b64decode(PNG_1x1_RED)
        resp1 = self._mock_response(
            [], status=302, headers={'Location': 'https://final.example/page'}
        )
        resp2 = self._mock_response([png], headers={'Content-Type': 'image/png'})
        with (
            patch(
                'odoo.addons.muk_ai.tools.url_fetch.socket.getaddrinfo',
                return_value=self._addrinfo('8.8.8.8'),
            ),
            patch(
                'odoo.addons.muk_ai.tools.url_fetch.urllib3.HTTPSConnectionPool',
                side_effect=[self._mock_pool(resp1), self._mock_pool(resp2)],
            ) as mock_pool_cls,
        ):
            result = fetch_url('https://start.example/go')
        self.assertEqual(result.url, 'https://final.example/page')
        self.assertEqual(result.body, png)
        self.assertEqual(result.content_type, 'image/png')
        self.assertEqual(mock_pool_cls.call_count, 2)

    def test_redirect_to_private_ip_blocked(self):
        resp1 = self._mock_response(
            [], status=302, headers={'Location': 'https://internal.example/secret'}
        )

        def _gai(host, *args, **kwargs):
            return self._addrinfo(
                '10.0.0.1' if host == 'internal.example' else '8.8.8.8'
            )

        with (
            patch(
                'odoo.addons.muk_ai.tools.url_fetch.socket.getaddrinfo',
                side_effect=_gai,
            ),
            patch(
                'odoo.addons.muk_ai.tools.url_fetch.urllib3.HTTPSConnectionPool',
                side_effect=[self._mock_pool(resp1)],
            ),
            self.assertRaises(UserError),
        ):
            fetch_url('https://start.example/go')

    def test_github_blob_rewritten_to_raw(self):
        resp = self._mock_response([b'code'], headers={'Content-Type': 'text/plain'})
        with (
            patch(
                'odoo.addons.muk_ai.tools.url_fetch.socket.getaddrinfo',
                return_value=self._addrinfo('8.8.8.8'),
            ),
            patch(
                'odoo.addons.muk_ai.tools.url_fetch.urllib3.HTTPSConnectionPool',
                return_value=self._mock_pool(resp),
            ) as mock_pool_cls,
        ):
            result = fetch_url('https://github.com/muk-it/muk_web/blob/19.0/README.md')
        self.assertEqual(
            result.url,
            'https://raw.githubusercontent.com/muk-it/muk_web/19.0/README.md',
        )
        self.assertEqual(
            mock_pool_cls.call_args.kwargs['assert_hostname'],
            'raw.githubusercontent.com',
        )

    def test_pool_kwargs_accepted_by_real_urllib3(self):
        pool = urllib3.HTTPSConnectionPool(
            host='127.0.0.1',
            port=443,
            assert_hostname='example.com',
            server_hostname='example.com',
            timeout=urllib3.Timeout(connect=CONNECT_TIMEOUT, read=READ_TIMEOUT),
            retries=False,
        )
        try:
            conn = pool._new_conn()
            conn.close()
        finally:
            pool.close()
