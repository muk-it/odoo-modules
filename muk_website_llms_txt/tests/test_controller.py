from __future__ import annotations

from odoo.tests import tagged
from odoo.tests.common import HttpCase

from .common import LlmsTxtCommon


@tagged('post_install', '-at_install')
class TestLlmsTxtController(LlmsTxtCommon, HttpCase):
    """Test the streamed llms.txt routes, their headers and conditional replies."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.website = cls._setup_llms_website()
        cls.page = cls._create_page(
            'Llms Route Page',
            '/llms-route-page',
            'LLMS_ROUTE_BODY_MARKER',
        )
        cls.website._generate_llms_document('llms.txt')
        cls.website._generate_llms_document('llms-full.txt')

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_llms_txt_streams_the_stored_document(self):
        response = self.url_open('/llms.txt')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['Content-Type'], 'text/plain; charset=utf-8')
        stored = self.website._search_llms_document('llms.txt')
        self.assertEqual(response.content, stored.raw)
        self.assertIn('- [Llms Route Page]', response.text)

    def test_llms_txt_reports_the_stored_token_estimate(self):
        response = self.url_open('/llms.txt')
        stored = self.website._search_llms_document('llms.txt')
        self.assertEqual(response.headers['x-markdown-tokens'], stored.description)
        self.assertGreater(int(response.headers['x-markdown-tokens']), 0)

    def test_llms_txt_advertises_the_content_signal_policy(self):
        self.assertEqual(
            self.url_open('/llms.txt').headers['Content-Signal'],
            'ai-train=yes, search=yes, ai-input=yes',
        )
        self.website.llms_content_signal = 'input_only'
        self.assertEqual(
            self.url_open('/llms.txt').headers['Content-Signal'],
            'ai-train=no, search=no, ai-input=yes',
        )
        self.website.llms_content_signal = 'all'

    def test_llms_txt_is_cacheable_and_conditional(self):
        response = self.url_open('/llms.txt')
        self.assertIn('max-age', response.headers['Cache-Control'])
        etag = response.headers['ETag']
        cached = self.url_open('/llms.txt', headers={'If-None-Match': etag})
        self.assertEqual(cached.status_code, 304)
        self.assertFalse(cached.content)

    def test_rebuilding_invalidates_the_cached_etag(self):
        etag = self.url_open('/llms.txt').headers['ETag']
        self._create_page('Llms Etag Page', '/llms-route-etag', 'LLMS_ETAG_MARKER')
        self.website._generate_llms_document('llms.txt')
        response = self.url_open('/llms.txt', headers={'If-None-Match': etag})
        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(response.headers['ETag'], etag)
        self.assertIn('/llms-route-etag', response.text)

    def test_llms_txt_is_not_served_when_disabled(self):
        self.website.llms_txt_enabled = False
        self.assertEqual(self.url_open('/llms.txt').status_code, 404)
        self.website.llms_txt_enabled = True
        self.assertEqual(self.url_open('/llms.txt').status_code, 200)

    def test_llms_full_txt_streams_the_page_markdown(self):
        response = self.url_open('/llms-full.txt')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['Content-Type'], 'text/plain; charset=utf-8')
        self.assertIn('## Llms Route Page', response.text)
        self.assertIn('LLMS_ROUTE_BODY_MARKER', response.text)
        self.assertIn('x-markdown-tokens', response.headers)
        self.assertIn('Content-Signal', response.headers)

    def test_llms_full_txt_is_not_served_when_disabled(self):
        self.website.llms_full_txt_enabled = False
        self.assertEqual(self.url_open('/llms-full.txt').status_code, 404)
        self.website.llms_full_txt_enabled = True

    def test_a_dropped_document_is_rendered_on_the_next_request(self):
        self.website._search_llms_document('llms.txt').unlink()
        self.assertFalse(self.website._search_llms_document('llms.txt'))
        response = self.url_open('/llms.txt')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.text.startswith('#'))
        self.assertTrue(self.website._search_llms_document('llms.txt'))

    def test_the_documents_are_reachable_without_authentication(self):
        self.assertEqual(self.url_open('/llms.txt').status_code, 200)
        self.assertEqual(self.url_open('/llms-full.txt').status_code, 200)
