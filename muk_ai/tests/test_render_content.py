from __future__ import annotations

from odoo.addons.muk_ai.tests.common import AITestCommon, html_result
from odoo.addons.muk_ai.tools.url_fetch import FetchResult, page_icon, render_content


class TestRenderContent(AITestCommon):
    """Verify content routing by type for fetched pages."""

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_html_to_markdown(self):
        title, content = render_content(html_result())
        self.assertEqual(title, 'Hello World')
        self.assertIn('# Heading', content)
        self.assertNotIn('<p>', content)

    def test_html_mode_returns_source(self):
        title, content = render_content(html_result(), mode='html')
        self.assertEqual(title, 'Hello World')
        self.assertIn('<p>', content)

    def test_text_mode_plain_no_markdown(self):
        title, content = render_content(html_result(), mode='text')
        self.assertEqual(title, 'Hello World')
        self.assertIn('Heading', content)
        self.assertIn('First', content)
        self.assertNotIn('# Heading', content)
        self.assertNotIn('Home About', content)

    def test_json_pretty_printed(self):
        result = FetchResult(
            url='https://api.example.com/x',
            body=b'{"b":2,"a":1}',
            content_type='application/json',
            charset=None,
        )
        _title, content = render_content(result)
        self.assertIn('"b": 2', content)

    def test_plain_text_passthrough(self):
        result = FetchResult(
            url='https://example.com/x.txt',
            body=b'just text',
            content_type='text/plain',
            charset=None,
        )
        title, content = render_content(result)
        self.assertIsNone(title)
        self.assertEqual(content, 'just text')

    def test_charset_decoding(self):
        result = FetchResult(
            url='https://example.com/x.txt',
            body='café'.encode('latin-1'),
            content_type='text/plain',
            charset='latin-1',
        )
        _title, content = render_content(result)
        self.assertEqual(content, 'café')


class TestPageIcon(AITestCommon):
    """Verify the favicon a fetched page declares is resolved server-side."""

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _page(self, head: str, url: str = 'https://example.com/a/b') -> FetchResult:
        """Build an HTML fetch result whose ``<head>`` is ``head``."""
        body = f'<!doctype html><html><head>{head}</head><body>x</body></html>'
        return FetchResult(
            url=url,
            body=body.encode(),
            content_type='text/html',
            charset=None,
        )

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_declared_icon_is_absolutised_against_the_page_url(self):
        result = self._page('<link rel="icon" href="/static/fav.png"/>')
        self.assertEqual(page_icon(result), 'https://example.com/static/fav.png')

    def test_relative_icon_resolves_against_the_directory(self):
        result = self._page('<link rel="shortcut icon" href="fav.ico"/>')
        self.assertEqual(page_icon(result), 'https://example.com/a/fav.ico')

    def test_largest_declared_size_wins(self):
        result = self._page(
            '<link rel="icon" sizes="16x16" href="/small.png"/>'
            '<link rel="icon" sizes="180x180" href="/big.png"/>'
        )
        self.assertEqual(page_icon(result), 'https://example.com/big.png')

    def test_scalable_icon_outranks_any_pixel_size(self):
        result = self._page(
            '<link rel="icon" sizes="180x180" href="/big.png"/>'
            '<link rel="icon" sizes="any" href="/vector.svg"/>'
        )
        self.assertEqual(page_icon(result), 'https://example.com/vector.svg')

    def test_apple_touch_icon_counts_as_an_icon(self):
        result = self._page('<link rel="apple-touch-icon" href="/touch.png"/>')
        self.assertEqual(page_icon(result), 'https://example.com/touch.png')

    def test_unrelated_link_tags_are_ignored(self):
        result = self._page('<link rel="stylesheet" href="/site.css"/>')
        self.assertIsNone(page_icon(result))

    def test_inline_and_unsafe_schemes_are_refused(self):
        blob = 'data:image/png;base64,' + 'A' * 40000
        self.assertIsNone(page_icon(self._page(f'<link rel="icon" href="{blob}"/>')))
        self.assertIsNone(
            page_icon(self._page('<link rel="icon" href="javascript:alert(1)"/>'))
        )
        self.assertIsNone(
            page_icon(self._page('<link rel="icon" href="http://example.com/f.png"/>'))
        )

    def test_page_without_a_declared_icon_resolves_to_none(self):
        self.assertIsNone(page_icon(self._page('<title>x</title>')))

    def test_non_html_payload_has_no_icon(self):
        result = FetchResult(
            url='https://example.com/x.json',
            body=b'{}',
            content_type='application/json',
            charset=None,
        )
        self.assertIsNone(page_icon(result))
