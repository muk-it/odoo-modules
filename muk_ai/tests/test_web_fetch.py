from __future__ import annotations

import ipaddress
import itertools
import json
from unittest.mock import patch

from odoo.addons.muk_ai.tests.common import (
    HTML_PAGE,
    PNG_BYTES,
    PUBLIC_IP,
    AITestCommon,
    serve_web,
)
from odoo.addons.muk_ai.tools.url_fetch import (
    CONNECT_TIMEOUT,
    FAVICON_DEADLINE,
    MAX_REDIRECTS,
    URL_FETCH_MAX_BYTES,
    WEB_FETCH_MAX_CHARS,
    FetchResult,
    page_icon,
)

CHUNK = b'x' * (1 << 20)


class TestWebFetch(AITestCommon):
    """Verify the web_fetch tool: rendering, pagination and the SSRF guard."""

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _fetch(self, url: str, **arguments) -> dict:
        """Run the web_fetch tool as a chat dispatches it and decode its result."""
        text, _info = self.env['muk_mcp.tool']._call(
            'web_fetch', {'url': url, **arguments}, self.env
        )
        return json.loads(text)

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_a_page_renders_in_the_requested_mode(self):
        page = {
            'https://example.com/page': (200, {'Content-Type': 'text/html'}, HTML_PAGE)
        }
        for mode, present, absent in (
            (
                'markdown',
                (
                    '# Heading',
                    'First [paragraph](https://example.com/docs).',
                    '- one\n- two',
                    '```\ncode line\n```',
                ),
                ('<p>', 'var x = 1', 'color:red', 'Home About', 'copyright'),
            ),
            ('bogus', ('# Heading',), ('<p>',)),
            (
                'text',
                ('Heading', 'First paragraph', 'code line'),
                ('# Heading', '<p>', 'var x = 1', 'Home About', 'copyright'),
            ),
            (
                'html',
                ('<p>First <a href="/docs">', '<nav>Home About</nav>'),
                ('# Heading',),
            ),
        ):
            with self.subTest(mode=mode):
                with serve_web(page):
                    result = self._fetch('http://example.com/page', mode=mode)
                self.assertEqual(result['type'], 'web')
                self.assertEqual(result['url'], 'https://example.com/page')
                self.assertEqual(result['title'], 'Hello World')
                self.assertEqual(result['content_type'], 'text/html')
                self.assertEqual(result['bytes'], len(HTML_PAGE))
                for snippet in present:
                    self.assertIn(snippet, result['content'])
                for snippet in absent:
                    self.assertNotIn(snippet, result['content'])

    def test_a_payload_renders_by_its_content_type(self):
        sniffed = b'<html><head><title>Sniffed</title></head><body><p>x</p></body>'
        for content_type, body, mode, title, content in (
            ('application/json', b'{"b":2,"a":1}', 'markdown', None, '{\n  "b": 2'),
            ('application/json', b'{"b":2', 'text', None, '{"b":2'),
            ('application/json', b'{"b":2,"a":1}', 'html', None, '{"b":2,"a":1}'),
            ('text/plain; charset=latin-1', b'caf\xe9', 'markdown', None, 'caf\xe9'),
            ('image/png', PNG_BYTES, 'markdown', None, 'not rendered as text'),
            ('', sniffed, 'markdown', 'Sniffed', 'x'),
        ):
            with self.subTest(content_type=content_type, mode=mode):
                url = 'https://example.com/payload'
                with serve_web({url: (200, {'Content-Type': content_type}, body)}):
                    result = self._fetch(url, mode=mode)
                self.assertEqual(result['title'], title)
                self.assertIn(content, result['content'])

    def test_a_long_page_is_read_window_by_window(self):
        total = WEB_FETCH_MAX_CHARS + 500
        url = 'https://example.com/long'
        page = {url: (200, {'Content-Type': 'text/plain'}, b'x' * total)}
        for arguments, offset, size, next_offset in (
            ({}, 0, WEB_FETCH_MAX_CHARS, WEB_FETCH_MAX_CHARS),
            ({'max_chars': 10**9}, 0, WEB_FETCH_MAX_CHARS, WEB_FETCH_MAX_CHARS),
            ({'max_chars': 100}, 0, 100, 100),
            ({'offset': -5, 'max_chars': 0}, 0, 1, 1),
            ({'offset': WEB_FETCH_MAX_CHARS}, WEB_FETCH_MAX_CHARS, 500, None),
            ({'offset': 10**7}, 10**7, 0, None),
        ):
            with self.subTest(arguments=arguments):
                with serve_web(page):
                    result = self._fetch(url, **arguments)
                self.assertEqual(result['offset'], offset)
                self.assertEqual(result['next_offset'], next_offset)
                self.assertEqual(result['truncated'], next_offset is not None)
                self.assertEqual(result['total_chars'], total)
                window, _, marker = result['content'].partition('\n\n')
                if size:
                    self.assertEqual(window, 'x' * size)
                else:
                    self.assertIn('no content at offset', window)
                self.assertEqual(
                    f'offset={next_offset} for more' in marker, next_offset is not None
                )

    def test_page_icon_picks_the_best_declared_https_icon(self):
        html = 'text/html'
        for content_type, links, icon in (
            (html, [('icon', '/fav.png', '')], '/fav.png'),
            (html, [('shortcut icon', 'fav.ico', '')], '/a/fav.ico'),
            (html, [('apple-touch-icon', '/t.png', '')], '/t.png'),
            (
                html,
                [('icon', '/s.png', '16x16'), ('icon', '/b.png', '180x180')],
                '/b.png',
            ),
            (
                html,
                [('icon', '/b.png', '180x180'), ('icon', '/v.svg', 'any')],
                '/v.svg',
            ),
            (html, [('stylesheet', '/site.css', '')], None),
            (html, [('icon', 'data:image/png;base64,AA', '')], None),
            (html, [('icon', 'javascript:alert(1)', '')], None),
            (html, [('icon', 'http://example.com/f.png', '')], None),
            (html, [], None),
            ('application/json', [('icon', '/fav.png', '')], None),
        ):
            with self.subTest(links=links, content_type=content_type):
                head = ''.join(
                    f'<link rel="{rel}" href="{href}" sizes="{sizes}"/>'
                    for rel, href, sizes in links
                )
                body = f'<html><head>{head}</head><body>x</body></html>'.encode()
                result = FetchResult(
                    'https://example.com/a/b', body, content_type, None
                )
                self.assertEqual(
                    page_icon(result), icon and f'https://example.com{icon}'
                )

    def test_the_guard_refuses_unsafe_targets(self):
        go = 'https://example.com/go'
        intra = {'intra.test': ('10.0.0.1',)}
        oversized = [CHUNK] * (URL_FETCH_MAX_BYTES // len(CHUNK) + 1)
        private = 'is not publicly routable'
        for url, pages, dns, error, hops in (
            ('ftp://example.com/x', {}, {}, 'only accepts https://', 0),
            ('https:///x', {}, {}, 'missing hostname', 0),
            ('http://intra.test/', {}, intra, private, 0),
            ('https://localhost/', {}, {'localhost': ('127.0.0.1',)}, private, 0),
            ('https://meta.test/', {}, {'meta.test': ('169.254.169.254',)}, private, 0),
            ('https://six.test/', {}, {'six.test': ('::1',)}, private, 0),
            (
                'https://mix.test/',
                {},
                {'mix.test': (PUBLIC_IP, '192.168.1.1')},
                private,
                0,
            ),
            ('https://gone.test/', {}, {'gone.test': None}, 'DNS lookup failed', 0),
            ('https://void.test/', {}, {'void.test': ()}, 'returned no addresses', 0),
            (
                go,
                {go: (302, {'Location': 'https://intra.test/'}, b'')},
                intra,
                private,
                1,
            ),
            (
                go,
                {go: (302, {'Location': '/go'}, b'')},
                {},
                'too many',
                MAX_REDIRECTS + 1,
            ),
            (go, {go: (302, {}, b'')}, {}, 'had no Location', 1),
            (go, {}, {}, 'HTTP 404', 1),
            (go, {go: (200, {}, oversized)}, {}, 'byte cap', 1),
        ):
            with self.subTest(url=url, error=error):
                with serve_web(pages, dns) as connections:
                    result = self._fetch(url)
                self.assertEqual(result['url'], url)
                self.assertIn(error, result['error'])
                self.assertNotIn('content', result)
                self.assertEqual(len(connections), hops)
                self.assertTrue(
                    all(ipaddress.ip_address(c['ip']).is_global for c in connections)
                )

    def test_a_public_page_is_read_over_the_validated_address(self):
        raw = 'https://raw.githubusercontent.com/muk-it/muk_web/20.0/README.md'
        pages = {
            raw: (301, {'Location': 'https://docs.test/readme'}, b''),
            'https://docs.test/readme': (200, {'Content-Type': 'text/plain'}, b'# Hi'),
            'https://docs.test/favicon.ico': (302, {'Location': '/icon.png'}, b''),
            'https://docs.test/icon.png': (200, {}, PNG_BYTES),
        }
        dns = {'raw.githubusercontent.com': ('185.199.108.133',)}
        with (
            serve_web(pages, dns) as connections,
            patch(
                'odoo.addons.muk_ai.tools.url_fetch.monotonic',
                side_effect=itertools.count(0, FAVICON_DEADLINE * 2 / 3),
            ),
        ):
            result = self._fetch('http://github.com/muk-it/muk_web/blob/20.0/README.md')
        self.assertEqual(result['url'], 'https://docs.test/readme')
        self.assertEqual(result['content'], '# Hi')
        self.assertEqual(result['icon'], '/muk_ai/source/icon/docs.test')
        self.assertEqual(
            [(c['ip'], c['host'], c['url']) for c in connections],
            [
                ('185.199.108.133', 'raw.githubusercontent.com', raw),
                (PUBLIC_IP, 'docs.test', 'https://docs.test/readme'),
                (PUBLIC_IP, 'docs.test', 'https://docs.test/favicon.ico'),
            ],
        )
        timeouts = [c['timeout'].connect_timeout for c in connections]
        self.assertEqual(timeouts[:2], [CONNECT_TIMEOUT, CONNECT_TIMEOUT])
        self.assertLessEqual(timeouts[2], FAVICON_DEADLINE)
        cached = self.env['ir.attachment'].search(
            [('url', '=', '/muk_ai/source/icon/docs.test')]
        )
        self.assertEqual(len(cached), 1)
        self.assertFalse(cached.raw)
