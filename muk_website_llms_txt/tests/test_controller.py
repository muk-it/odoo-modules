from __future__ import annotations

from odoo.tests import tagged
from odoo.tests.common import HttpCase


@tagged('post_install', '-at_install')
class TestLlmsTxtController(HttpCase):
    """Test the llms.txt routes and markdown content negotiation."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.website = cls.env['website'].search([], limit=1)
        cls.website.write(
            {
                'llms_txt_enabled': True,
                'llms_full_txt_enabled': True,
                'llms_content_signal': 'all',
                'llms_link_headers_enabled': True,
            }
        )

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_llms_txt_returns_200(self):
        response = self.url_open('/llms.txt')
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/plain', response.headers.get('Content-Type', ''))

    def test_llms_txt_content_format(self):
        response = self.url_open('/llms.txt')
        content = response.text
        self.assertTrue(content.startswith('#'))

    def test_llms_txt_has_token_header(self):
        response = self.url_open('/llms.txt')
        self.assertIn('x-markdown-tokens', response.headers)
        token_count = int(response.headers['x-markdown-tokens'])
        self.assertGreater(token_count, 0)

    def test_llms_txt_has_content_signal_header(self):
        response = self.url_open('/llms.txt')
        self.assertIn('Content-Signal', response.headers)
        self.assertIn('ai-train=yes', response.headers['Content-Signal'])

    def test_llms_txt_disabled(self):
        self.website.llms_txt_enabled = False
        response = self.url_open('/llms.txt')
        self.assertEqual(response.status_code, 404)
        self.website.llms_txt_enabled = True

    def test_llms_full_txt_returns_200(self):
        response = self.url_open('/llms-full.txt')
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/plain', response.headers.get('Content-Type', ''))

    def test_llms_full_txt_disabled(self):
        self.website.llms_full_txt_enabled = False
        response = self.url_open('/llms-full.txt')
        self.assertEqual(response.status_code, 404)
        self.website.llms_full_txt_enabled = True

    def test_llms_full_txt_has_headers(self):
        response = self.url_open('/llms-full.txt')
        self.assertIn('x-markdown-tokens', response.headers)
        self.assertIn('Content-Signal', response.headers)

    def test_llms_txt_contains_pages_section(self):
        response = self.url_open('/llms.txt')
        content = response.text
        self.assertIn('## Pages', content)

    def test_content_signal_none(self):
        self.website.llms_content_signal = 'none'
        response = self.url_open('/llms.txt')
        self.assertIn('ai-train=no', response.headers['Content-Signal'])
        self.website.llms_content_signal = 'all'

    def test_markdown_negotiation(self):
        response = self.url_open(
            '/',
            headers={'Accept': 'text/markdown'},
        )
        content_type = response.headers.get('Content-Type', '')
        if 'text/markdown' in content_type:
            self.assertIn('x-markdown-tokens', response.headers)
            self.assertIn('Vary', response.headers)
            self.assertIn('Accept', response.headers['Vary'])

    def test_markdown_negotiation_disabled(self):
        self.website.llms_txt_enabled = False
        response = self.url_open(
            '/',
            headers={'Accept': 'text/markdown'},
        )
        content_type = response.headers.get('Content-Type', '')
        if 'text/markdown' in content_type:
            self.assertIn('x-markdown-tokens', response.headers)
        self.website.llms_txt_enabled = True

    def test_normal_request_not_affected(self):
        response = self.url_open('/')
        content_type = response.headers.get('Content-Type', '')
        self.assertIn('text/html', content_type)

    def test_link_header_present(self):
        response = self.url_open('/')
        link = response.headers.get('Link', '')
        self.assertIn('</llms.txt>', link)
        self.assertIn('rel="describedby"', link)

    def test_link_header_advertises_full(self):
        response = self.url_open('/')
        link = response.headers.get('Link', '')
        self.assertIn('</llms-full.txt>', link)

    def test_link_header_advertises_markdown_alternate(self):
        response = self.url_open('/')
        link = response.headers.get('Link', '')
        self.assertIn('rel="alternate"', link)
        self.assertIn('type="text/markdown"', link)

    def test_link_header_sets_vary_accept(self):
        response = self.url_open('/')
        self.assertIn('Accept', response.headers.get('Vary', ''))

    def test_link_header_disabled(self):
        self.website.llms_link_headers_enabled = False
        response = self.url_open('/')
        self.assertNotIn('llms.txt', response.headers.get('Link', ''))
        self.assertNotIn('text/markdown', response.headers.get('Link', ''))
        self.website.llms_link_headers_enabled = True

    def test_link_header_omits_disabled_resources(self):
        self.website.llms_full_txt_enabled = False
        response = self.url_open('/')
        link = response.headers.get('Link', '')
        self.assertIn('</llms.txt>', link)
        self.assertNotIn('</llms-full.txt>', link)
        self.website.llms_full_txt_enabled = True
