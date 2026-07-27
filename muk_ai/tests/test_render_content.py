from odoo.addons.muk_ai.tests.common import AITestCommon, html_result
from odoo.addons.muk_ai.tools.url_fetch import FetchResult, render_content


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
