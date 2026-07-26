from odoo.tests.common import TransactionCase, tagged

from odoo.addons.muk_website_llms_txt.tools.converter import (
    build_content_signal,
    estimate_tokens,
    extract_jsonld,
    extract_metadata,
    html_to_markdown,
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

GRAPH_PAGE = """
<html><head>
<script type="application/ld+json">
{"@context": "https://schema.org", "@graph": [
    {"@type": "WebPage", "name": "Shop"},
    {"@type": ["Product"], "name": "Graph Mug",
     "offers": [{"@type": "Offer", "price": "1.50", "priceCurrency": "EUR"}]}
]}
</script>
</head><body><div id="wrap"><p>Graph body</p></div></body></html>
"""


@tagged('post_install', '-at_install')
class TestConverter(TransactionCase):
    """Test the HTML-to-markdown conversion, metadata extraction and signals."""

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_inline_markup_text_survives_the_conversion(self):
        html = (
            '<h1>Title</h1><h2>Subtitle</h2>'
            '<p><strong>Bold</strong> and <em>italic</em></p>'
            '<ul><li>Item 1</li><li>Item 2</li></ul>'
            '<a href="https://example.com">Click here</a>'
            '<pre><code>code here</code></pre>'
            '<blockquote><p>A quoted text</p></blockquote>'
        )
        result = html_to_markdown(html)
        for text in (
            'Title',
            'Subtitle',
            'Bold',
            'italic',
            'Item 1',
            'Item 2',
            'Click here',
            'code here',
            'A quoted text',
        ):
            self.assertIn(text, result)

    def test_script_and_style_content_is_dropped(self):
        html = (
            '<div><p>Content</p><script>alert("xss")</script>'
            '<style>.a{color:red}</style></div>'
        )
        result = html_to_markdown(html)
        self.assertIn('Content', result)
        self.assertNotIn('alert', result)
        self.assertNotIn('color:red', result)

    def test_navigation_and_footer_are_dropped(self):
        html = (
            '<nav>Navigation</nav><main><p>Main content</p></main>'
            '<footer>Footer</footer>'
        )
        result = html_to_markdown(html)
        self.assertIn('Main content', result)
        self.assertNotIn('Navigation', result)
        self.assertNotIn('Footer', result)

    def test_wrap_is_preferred_over_main_and_over_the_body(self):
        wrapped = html_to_markdown(
            '<div>Outside</div><main>In main</main><div id="wrap">In wrap</div>'
        )
        self.assertIn('In wrap', wrapped)
        self.assertNotIn('Outside', wrapped)
        self.assertIn(
            'In main', html_to_markdown('<div>Outside</div><main>In main</main>')
        )
        self.assertIn('Bare body', html_to_markdown('<p>Bare body</p>'))

    def test_blank_line_runs_are_collapsed(self):
        html = '<p>One</p>' + '<br/>' * 8 + '<p>Two</p>'
        result = html_to_markdown(html)
        self.assertNotIn('\n\n\n', result)
        self.assertIn('One', result)
        self.assertIn('Two', result)

    def test_empty_and_bytes_input(self):
        self.assertEqual(html_to_markdown(''), '')
        self.assertEqual(html_to_markdown(None), '')
        self.assertEqual(page_to_agent_markdown(''), '')
        self.assertIn('Bytes content', html_to_markdown(b'<p>Bytes content</p>'))
        self.assertIn(
            'Bytes body',
            page_to_agent_markdown(b'<div id="wrap"><p>Bytes body</p></div>'),
        )

    def test_estimate_tokens(self):
        self.assertEqual(estimate_tokens(''), 0)
        self.assertEqual(estimate_tokens(None), 0)
        self.assertEqual(estimate_tokens('Hello world this is a test'), int(6 * 1.3))

    def test_build_content_signal_maps_every_policy(self):
        self.assertEqual(
            build_content_signal('all'), 'ai-train=yes, search=yes, ai-input=yes'
        )
        self.assertEqual(
            build_content_signal('search_input'),
            'ai-train=no, search=yes, ai-input=yes',
        )
        self.assertEqual(
            build_content_signal('input_only'), 'ai-train=no, search=no, ai-input=yes'
        )
        self.assertEqual(
            build_content_signal('none'), 'ai-train=no, search=no, ai-input=no'
        )
        self.assertEqual(
            build_content_signal('unknown'), 'ai-train=yes, search=yes, ai-input=yes'
        )

    def test_complex_page(self):
        html = """
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
        """
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

    def test_extract_jsonld_skips_unusable_scripts(self):
        html = (
            '<script type="application/ld+json">{not json}</script>'
            '<script type="application/ld+json"></script>'
            '<script type="text/javascript">{"@type": "Product"}</script>'
            '<script>{"@type": "Product"}</script>'
        )
        self.assertEqual(extract_jsonld(html), [])

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

    def test_extract_metadata_prefers_open_graph_title(self):
        html = (
            '<html><head><title>Document title</title>'
            '<meta property="og:title" content="Social title"/>'
            '<meta name="description" content="First"/>'
            '<meta property="og:description" content="Second"/>'
            '<meta name="empty" content=" "/>'
            '</head><body></body></html>'
        )
        meta = extract_metadata(html)
        self.assertEqual(meta['title'], 'Social title')
        self.assertEqual(meta['description'], 'First')
        self.assertNotIn('image', meta)

    def test_extract_metadata_empty(self):
        self.assertEqual(extract_metadata(None), {})
        self.assertEqual(extract_metadata('<p>no head</p>'), {})

    def test_agent_markdown_has_frontmatter(self):
        result = page_to_agent_markdown(PRODUCT_PAGE)
        self.assertTrue(result.startswith('---'))
        self.assertIn('title: "Cool Mug"', result)
        self.assertIn('description: "A nice ceramic mug."', result)

    def test_agent_markdown_frontmatter_stays_single_line_and_quoted(self):
        html = (
            '<html><head><title>He said "hi"\nand left</title>'
            '</head><body><div id="wrap"><p>Body</p></div></body></html>'
        )
        result = page_to_agent_markdown(html)
        frontmatter = result.split('---')[1]
        self.assertIn('title: "He said \\"hi\\" and left"', frontmatter)
        self.assertEqual(len(frontmatter.strip().splitlines()), 1)

    def test_agent_markdown_preserves_jsonld(self):
        result = page_to_agent_markdown(PRODUCT_PAGE)
        self.assertIn('```json', result)
        self.assertIn('"@type": "Product"', result)
        self.assertIn('"sku": "MUG-1"', result)

    def test_agent_markdown_keeps_several_jsonld_objects_as_a_list(self):
        html = (
            '<script type="application/ld+json">{"@type": "Product", "name": "A"}'
            '</script>'
            '<script type="application/ld+json">{"@type": "Organization"}</script>'
            '<div id="wrap"><p>Body</p></div>'
        )
        result = page_to_agent_markdown(html)
        self.assertIn('```json\n[', result)

    def test_agent_markdown_product_summary(self):
        result = page_to_agent_markdown(PRODUCT_PAGE)
        self.assertIn('**Product:**', result)
        self.assertIn('Cool Mug', result)
        self.assertIn('9.90 EUR', result)
        self.assertIn('InStock', result)
        self.assertIn('SKU: MUG-1', result)
        self.assertIn('Brand: MuKware', result)

    def test_agent_markdown_product_summary_walks_a_jsonld_graph(self):
        result = page_to_agent_markdown(GRAPH_PAGE)
        self.assertIn('**Product:** Graph Mug · 1.50 EUR', result)
        self.assertIn('Graph body', result)

    def test_agent_markdown_keeps_body(self):
        result = page_to_agent_markdown(PRODUCT_PAGE)
        self.assertIn('A nice ceramic mug.', result)

    def test_agent_markdown_without_metadata(self):
        result = page_to_agent_markdown('<div id="wrap"><p>Plain body</p></div>')
        self.assertNotIn('---', result)
        self.assertNotIn('```json', result)
        self.assertIn('Plain body', result)
