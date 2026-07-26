from odoo.addons.muk_ai.tests.common import HTML_PAGE, AITestCommon
from odoo.addons.muk_ai.tools.parser import extract_title, html_to_markdown


class TestHtmlMarkdown(AITestCommon):
    """Verify the lxml HTML-to-Markdown converter and title extraction."""

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

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
