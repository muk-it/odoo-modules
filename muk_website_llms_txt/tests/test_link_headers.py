from __future__ import annotations

from odoo.tests import tagged
from odoo.tests.common import HttpCase

from .common import LlmsTxtCommon


@tagged('post_install', '-at_install')
class TestLlmsTxtLinkHeaders(LlmsTxtCommon, HttpCase):
    """Test the RFC 8288 agent-discovery Link headers added to website pages."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.website = cls._setup_llms_website()
        cls.page = cls._create_page(
            'Llms Link Page',
            '/llms-link-page',
            'LLMS_LINK_MARKER',
        )

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_link_header_advertises_both_documents(self):
        link = self.url_open('/llms-link-page').headers['Link']
        self.assertIn('</llms.txt>; rel="describedby"', link)
        self.assertIn('</llms-full.txt>; rel="describedby"', link)

    def test_link_header_advertises_the_page_as_a_markdown_alternate(self):
        link = self.url_open('/llms-link-page').headers['Link']
        self.assertIn(
            '</llms-link-page>; rel="alternate"; type="text/markdown"',
            link,
        )

    def test_link_header_sets_vary_accept_once(self):
        vary = self.url_open('/llms-link-page').headers['Vary']
        self.assertIn('Accept', vary)
        self.assertEqual(vary.lower().count('accept'), 1)

    def test_link_header_omits_a_disabled_document(self):
        self.website.llms_full_txt_enabled = False
        link = self.url_open('/llms-link-page').headers['Link']
        self.assertIn('</llms.txt>', link)
        self.assertNotIn('</llms-full.txt>', link)
        self.website.llms_full_txt_enabled = True

    def test_link_header_is_absent_when_the_feature_is_disabled(self):
        self.website.llms_link_headers_enabled = False
        response = self.url_open('/llms-link-page')
        self.assertNotIn('Link', response.headers)
        self.website.llms_link_headers_enabled = True

    def test_link_header_is_absent_on_a_missing_page(self):
        response = self.url_open('/llms-link-does-not-exist')
        self.assertEqual(response.status_code, 404)
        self.assertNotIn('Link', response.headers)

    def test_link_header_is_absent_on_the_plain_text_documents(self):
        self.assertNotIn('Link', self.url_open('/llms.txt').headers)

    def test_link_header_is_absent_on_a_markdown_response(self):
        response = self.url_open('/llms-link-page', headers={'Accept': 'text/markdown'})
        self.assertIn('text/markdown', response.headers['Content-Type'])
        self.assertNotIn('Link', response.headers)

    def test_link_header_value_only_lists_enabled_resources(self):
        self.website.write({'llms_txt_enabled': False, 'llms_full_txt_enabled': False})
        self.assertEqual(self.website._get_llms_link_header(), '')
        self.assertEqual(
            self.website._get_llms_link_header('/page'),
            '</page>; rel="alternate"; type="text/markdown"; title="Markdown"',
        )
        self.website.write({'llms_txt_enabled': True, 'llms_full_txt_enabled': True})
