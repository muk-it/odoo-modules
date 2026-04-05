from odoo.tests import tagged
from odoo.tests.common import HttpCase


@tagged('post_install', '-at_install')
class TestLlmsTxtController(HttpCase):

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.website = cls.env['website'].search([], limit=1)
        cls.website.write({
            'llms_txt_enabled': True,
            'llms_full_txt_enabled': True,
            'llms_content_signal': 'all',
        })

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
