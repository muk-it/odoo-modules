from unittest.mock import patch

from odoo.exceptions import UserError

from odoo.addons.muk_ai.tests.common import AITestCommon
from odoo.addons.muk_ai.tools.parser import extract_title, html_to_markdown
from odoo.addons.muk_ai.tools.url_fetch import (
    WEB_FETCH_MAX_CHARS,
    FetchResult,
    render_content,
)
from odoo.addons.muk_mcp.core.tool import get_tool_index

HTML_PAGE = (
    b'<!doctype html><html><head><title>  Hello   World </title>'
    b'<style>.x{color:red}</style></head>'
    b'<body><nav>Home About</nav>'
    b'<main><h1>Heading</h1><p>First <a href="/docs">paragraph</a>.</p>'
    b'<script>var x = 1;</script>'
    b'<ul><li>one</li><li>two</li></ul>'
    b'<pre><code>code line</code></pre></main>'
    b'<footer>copyright</footer></body></html>'
)


def _html_result(url='https://example.com/page'):
    return FetchResult(url=url, body=HTML_PAGE, content_type='text/html', charset=None)


class TestHtmlMarkdown(AITestCommon):
    """Verify the lxml HTML-to-Markdown converter and title extraction."""

    def test_title(self):
        self.assertEqual(extract_title(HTML_PAGE.decode()), 'Hello World')

    def test_headings_and_paragraph(self):
        md = html_to_markdown(HTML_PAGE.decode(), 'https://example.com/page')
        self.assertIn('# Heading', md)
        self.assertIn('First', md)

    def test_links_absolutised(self):
        md = html_to_markdown(HTML_PAGE.decode(), 'https://example.com/page')
        self.assertIn('[paragraph](https://example.com/docs)', md)

    def test_list_rendered(self):
        md = html_to_markdown(HTML_PAGE.decode(), '')
        self.assertIn('- one', md)
        self.assertIn('- two', md)

    def test_code_block_fenced(self):
        md = html_to_markdown(HTML_PAGE.decode(), '')
        self.assertIn('```', md)
        self.assertIn('code line', md)

    def test_boilerplate_and_script_stripped(self):
        md = html_to_markdown(HTML_PAGE.decode(), '')
        self.assertNotIn('var x = 1', md)
        self.assertNotIn('color:red', md)
        self.assertNotIn('Home About', md)
        self.assertNotIn('copyright', md)

    def test_unparseable_returns_empty(self):
        self.assertEqual(html_to_markdown('', ''), '')


class TestRenderContent(AITestCommon):
    """Verify content routing by type for fetched pages."""

    def test_html_to_markdown(self):
        title, content = render_content(_html_result())
        self.assertEqual(title, 'Hello World')
        self.assertIn('# Heading', content)
        self.assertNotIn('<p>', content)

    def test_html_mode_returns_source(self):
        title, content = render_content(_html_result(), mode='html')
        self.assertEqual(title, 'Hello World')
        self.assertIn('<p>', content)

    def test_text_mode_plain_no_markdown(self):
        title, content = render_content(_html_result(), mode='text')
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


class TestWebFetchTool(AITestCommon):
    """Verify the web_fetch MCP tool result shape, pagination, and registration."""

    def test_success_returns_web_source_descriptor(self):
        with patch('odoo.addons.muk_ai.mcp.web.fetch_url', return_value=_html_result()):
            result = self.env['muk_mcp.mixin']._mcp_web_fetch(
                url='https://example.com/page',
            )
        self.assertEqual(result['type'], 'web')
        self.assertEqual(result['url'], 'https://example.com/page')
        self.assertEqual(result['title'], 'Hello World')
        self.assertIn('# Heading', result['content'])
        self.assertEqual(result['content_type'], 'text/html')
        self.assertEqual(result['bytes'], len(HTML_PAGE))
        self.assertFalse(result['truncated'])
        self.assertIsNone(result['next_offset'])

    def test_pagination_truncates_with_marker(self):
        big = FetchResult(
            url='https://example.com/big',
            body=b'x' * 500,
            content_type='text/plain',
            charset=None,
        )
        with patch('odoo.addons.muk_ai.mcp.web.fetch_url', return_value=big):
            result = self.env['muk_mcp.mixin']._mcp_web_fetch(
                url='https://example.com/big',
                max_chars=100,
            )
        self.assertTrue(result['truncated'])
        self.assertEqual(result['next_offset'], 100)
        self.assertEqual(result['total_chars'], 500)
        self.assertIn('offset=100', result['content'])

    def test_offset_reads_next_window(self):
        big = FetchResult(
            url='https://example.com/big',
            body=b'x' * 500,
            content_type='text/plain',
            charset=None,
        )
        with patch('odoo.addons.muk_ai.mcp.web.fetch_url', return_value=big):
            result = self.env['muk_mcp.mixin']._mcp_web_fetch(
                url='https://example.com/big',
                offset=450,
                max_chars=100,
            )
        self.assertFalse(result['truncated'])
        self.assertEqual(result['offset'], 450)

    def test_offset_beyond_total(self):
        with patch('odoo.addons.muk_ai.mcp.web.fetch_url', return_value=_html_result()):
            result = self.env['muk_mcp.mixin']._mcp_web_fetch(
                url='https://example.com/page',
                offset=10_000_000,
            )
        self.assertIn('no content at offset', result['content'])
        self.assertFalse(result['truncated'])

    def test_max_chars_capped(self):
        big = FetchResult(
            url='https://example.com/big',
            body=b'x' * 10,
            content_type='text/plain',
            charset=None,
        )
        with patch('odoo.addons.muk_ai.mcp.web.fetch_url', return_value=big):
            result = self.env['muk_mcp.mixin']._mcp_web_fetch(
                url='https://example.com/big',
                max_chars=999_999_999,
            )
        self.assertLessEqual(len(result['content']), WEB_FETCH_MAX_CHARS)

    def test_mode_html_passthrough(self):
        with patch('odoo.addons.muk_ai.mcp.web.fetch_url', return_value=_html_result()):
            result = self.env['muk_mcp.mixin']._mcp_web_fetch(
                url='https://example.com/page',
                mode='html',
            )
        self.assertIn('<p>', result['content'])

    def test_invalid_mode_falls_back_to_markdown(self):
        with patch('odoo.addons.muk_ai.mcp.web.fetch_url', return_value=_html_result()):
            result = self.env['muk_mcp.mixin']._mcp_web_fetch(
                url='https://example.com/page',
                mode='bogus',
            )
        self.assertIn('# Heading', result['content'])

    def test_fetch_error_returned_not_raised(self):
        with patch(
            'odoo.addons.muk_ai.mcp.web.fetch_url',
            side_effect=UserError('@url: HTTP 404 for https://example.com/x.'),
        ):
            result = self.env['muk_mcp.mixin']._mcp_web_fetch(
                url='https://example.com/x',
            )
        self.assertEqual(result['url'], 'https://example.com/x')
        self.assertIn('404', result['error'])
        self.assertNotIn('content', result)

    def test_tool_registered_in_odoo_catalog(self):
        index = get_tool_index(self.env, registry='odoo')
        self.assertIn('web_fetch', index)
        self.assertEqual(index['web_fetch']['category'], 'read')
