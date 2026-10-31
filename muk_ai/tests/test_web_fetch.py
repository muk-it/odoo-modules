import base64
import json
from unittest.mock import patch

from odoo.exceptions import UserError

from odoo.addons.muk_ai.tests.common import (
    HTML_PAGE,
    AITestCommon,
    PNG_1x1,
    html_result,
)
from odoo.addons.muk_ai.tools.sources import extract_sources
from odoo.addons.muk_ai.tools.url_fetch import WEB_FETCH_MAX_CHARS, FetchResult
from odoo.addons.muk_mcp.core.tool import get_tool_index
from odoo.addons.muk_mcp.tools.protocol import ToolContent


class TestWebFetchTool(AITestCommon):
    """Verify the web_fetch MCP tool result shape, pagination, and registration."""

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_success_returns_web_source_descriptor(self):
        with patch('odoo.addons.muk_ai.mcp.web.fetch_url', return_value=html_result()):
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
        with patch('odoo.addons.muk_ai.mcp.web.fetch_url', return_value=html_result()):
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
        with patch('odoo.addons.muk_ai.mcp.web.fetch_url', return_value=html_result()):
            result = self.env['muk_mcp.mixin']._mcp_web_fetch(
                url='https://example.com/page',
                mode='html',
            )
        self.assertIn('<p>', result['content'])

    def test_invalid_mode_falls_back_to_markdown(self):
        with patch('odoo.addons.muk_ai.mcp.web.fetch_url', return_value=html_result()):
            result = self.env['muk_mcp.mixin']._mcp_web_fetch(
                url='https://example.com/page',
                mode='bogus',
            )
        self.assertIn('# Heading', result['content'])

    def test_a_file_comes_back_as_the_file_itself(self):
        url = 'https://example.com/payload'
        for content_type, body, content in (
            (
                'image/png',
                base64.b64decode(PNG_1x1),
                [{'type': 'image', 'data': PNG_1x1, 'mimeType': 'image/png'}],
            ),
            (
                'application/pdf',
                b'%PDF-1.4',
                [
                    {
                        'type': 'resource',
                        'resource': {
                            'uri': url,
                            'mimeType': 'application/pdf',
                            'name': 'payload',
                            'blob': 'JVBERi0xLjQ=',
                        },
                    }
                ],
            ),
            ('application/zip', b'PK', 'not rendered as text'),
        ):
            with self.subTest(content_type=content_type):
                fetched = FetchResult(
                    url=url, body=body, content_type=content_type, charset=None
                )
                with patch(
                    'odoo.addons.muk_ai.mcp.web.fetch_url', return_value=fetched
                ):
                    result, _info = self.env['muk_mcp.tool']._call(
                        'web_fetch', {'url': url}, self.env
                    )
                if isinstance(content, list):
                    self.assertIsInstance(result, ToolContent)
                    self.assertEqual(result[1:], content)
                    [source] = extract_sources('web_fetch', {'url': url}, result)
                    self.assertEqual(source['url'], url)
                else:
                    self.assertIn(content, json.loads(result)['content'])

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
