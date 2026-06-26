from odoo.tests.common import tagged, TransactionCase

from odoo.addons.muk_website_llms_txt.tools.converter import (
    html_to_markdown,
    estimate_tokens,
    build_content_signal,
    extract_jsonld,
    extract_metadata,
    page_to_agent_markdown,
)

PRODUCT_PAGE = """
<html>
<head>
    <title>Cool Mug</title>
    <meta name="description" content="A nice ceramic mug."/>
    <meta property="og:image" content="https://example.com/mug.jpg"/>
    <script type="application/ld+json">
    {"@context": "https://schema.org", "@type": "Product", "name": "Cool Mug",
     "sku": "MUG-1", "brand": {"@type": "Brand", "name": "MuKware"},
     "offers": {"@type": "Offer", "price": "9.90", "priceCurrency": "EUR",
                "availability": "https://schema.org/InStock"}}
    </script>
</head>
<body>
    <div id="wrap"><h1>Cool Mug</h1><p>A nice ceramic mug.</p></div>
</body>
</html>
"""


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

    def test_extract_jsonld(self):
        objects = extract_jsonld(PRODUCT_PAGE)
        self.assertEqual(len(objects), 1)
        self.assertEqual(objects[0]['@type'], 'Product')

    def test_extract_jsonld_empty(self):
        self.assertEqual(extract_jsonld('<p>no script</p>'), [])
        self.assertEqual(extract_jsonld(None), [])

    def test_extract_jsonld_flattens_arrays(self):
        html = (
            '<script type="application/ld+json">'
            '[{"@type": "Product", "name": "A"}, {"@type": "Breadcrumb"}]'
            '</script>'
            '<script type="application/ld+json">'
            '{"@type": "Organization", "name": "B"}</script>'
        )
        objects = extract_jsonld(html)
        self.assertEqual(len(objects), 3)
        self.assertTrue(all(isinstance(obj, dict) for obj in objects))

    def test_extract_metadata(self):
        meta = extract_metadata(PRODUCT_PAGE)
        self.assertEqual(meta['title'], 'Cool Mug')
        self.assertEqual(meta['description'], 'A nice ceramic mug.')
        self.assertEqual(meta['image'], 'https://example.com/mug.jpg')

    def test_agent_markdown_has_frontmatter(self):
        result = page_to_agent_markdown(PRODUCT_PAGE)
        self.assertTrue(result.startswith('---'))
        self.assertIn('title: "Cool Mug"', result)
        self.assertIn('description: "A nice ceramic mug."', result)

    def test_agent_markdown_preserves_jsonld(self):
        result = page_to_agent_markdown(PRODUCT_PAGE)
        self.assertIn('```json', result)
        self.assertIn('"@type": "Product"', result)
        self.assertIn('"sku": "MUG-1"', result)

    def test_agent_markdown_product_summary(self):
        result = page_to_agent_markdown(PRODUCT_PAGE)
        self.assertIn('**Product:**', result)
        self.assertIn('Cool Mug', result)
        self.assertIn('9.90 EUR', result)
        self.assertIn('InStock', result)
        self.assertIn('SKU: MUG-1', result)

    def test_agent_markdown_keeps_body(self):
        result = page_to_agent_markdown(PRODUCT_PAGE)
        self.assertIn('A nice ceramic mug.', result)

    def test_agent_markdown_without_metadata(self):
        result = page_to_agent_markdown('<div id="wrap"><p>Plain body</p></div>')
        self.assertNotIn('---', result)
        self.assertNotIn('```json', result)
        self.assertIn('Plain body', result)
