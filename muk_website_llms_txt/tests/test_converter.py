from odoo.tests.common import tagged, TransactionCase

from odoo.addons.muk_website_llms_txt.tools.converter import (
    html_to_markdown,
    estimate_tokens,
    build_content_signal,
)


@tagged('post_install', '-at_install')
class TestConverter(TransactionCase):

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_simple_paragraph(self):
        html = '<p>Hello world</p>'
        result = html_to_markdown(html)
        self.assertIn('Hello world', result)

    def test_heading_preserved(self):
        html = '<h1>Title</h1><h2>Subtitle</h2>'
        result = html_to_markdown(html)
        self.assertIn('Title', result)
        self.assertIn('Subtitle', result)

    def test_link_text_preserved(self):
        html = '<a href="https://example.com">Click here</a>'
        result = html_to_markdown(html)
        self.assertIn('Click here', result)

    def test_bold_text_preserved(self):
        html = '<p><strong>Bold</strong> and <em>italic</em></p>'
        result = html_to_markdown(html)
        self.assertIn('Bold', result)
        self.assertIn('italic', result)

    def test_list_items_preserved(self):
        html = '<ul><li>Item 1</li><li>Item 2</li></ul>'
        result = html_to_markdown(html)
        self.assertIn('Item 1', result)
        self.assertIn('Item 2', result)

    def test_strip_script_tags(self):
        html = '<div><p>Content</p><script>alert("xss")</script></div>'
        result = html_to_markdown(html)
        self.assertIn('Content', result)
        self.assertNotIn('alert', result)

    def test_strip_nav_and_footer(self):
        html = '<nav>Navigation</nav><main><p>Main content</p></main><footer>Footer</footer>'
        result = html_to_markdown(html)
        self.assertIn('Main content', result)
        self.assertNotIn('Navigation', result)
        self.assertNotIn('Footer', result)

    def test_extract_main_content(self):
        html = '<div>Outside</div><main><p>Inside main</p></main>'
        result = html_to_markdown(html)
        self.assertIn('Inside main', result)

    def test_extract_wrap_content(self):
        html = '<div>Outside</div><div id="wrap"><p>Inside wrap</p></div>'
        result = html_to_markdown(html)
        self.assertIn('Inside wrap', result)

    def test_empty_input(self):
        self.assertEqual(html_to_markdown(''), '')
        self.assertEqual(html_to_markdown(None), '')

    def test_code_preserved(self):
        html = '<pre><code>code here</code></pre>'
        result = html_to_markdown(html)
        self.assertIn('code here', result)

    def test_blockquote_preserved(self):
        html = '<blockquote><p>A quoted text</p></blockquote>'
        result = html_to_markdown(html)
        self.assertIn('A quoted text', result)

    def test_bytes_input(self):
        html = b'<p>Bytes content</p>'
        result = html_to_markdown(html)
        self.assertIn('Bytes content', result)

    def test_estimate_tokens_empty(self):
        self.assertEqual(estimate_tokens(''), 0)
        self.assertEqual(estimate_tokens(None), 0)

    def test_estimate_tokens_basic(self):
        text = 'Hello world this is a test'
        tokens = estimate_tokens(text)
        self.assertEqual(tokens, int(6 * 1.3))

    def test_build_content_signal_all(self):
        result = build_content_signal('all')
        self.assertEqual(result, 'ai-train=yes, search=yes, ai-input=yes')

    def test_build_content_signal_none(self):
        result = build_content_signal('none')
        self.assertEqual(result, 'ai-train=no, search=no, ai-input=no')

    def test_build_content_signal_search_input(self):
        result = build_content_signal('search_input')
        self.assertEqual(result, 'ai-train=no, search=yes, ai-input=yes')

    def test_build_content_signal_invalid(self):
        result = build_content_signal('unknown')
        self.assertEqual(result, 'ai-train=yes, search=yes, ai-input=yes')

    def test_complex_page(self):
        html = '''
        <html>
        <body>
            <nav class="o_header_standard">Menu</nav>
            <div id="wrap">
                <h1>Welcome</h1>
                <p>This is a <strong>great</strong> website.</p>
                <ul>
                    <li>Feature 1</li>
                    <li>Feature 2</li>
                </ul>
                <a href="/contact">Contact us</a>
            </div>
            <footer class="o_footer">Copyright</footer>
        </body>
        </html>
        '''
        result = html_to_markdown(html)
        self.assertIn('Welcome', result)
        self.assertIn('great', result)
        self.assertIn('Feature 1', result)
        self.assertIn('Contact us', result)
        self.assertNotIn('Menu', result)
        self.assertNotIn('Copyright', result)
