from __future__ import annotations

from unittest.mock import patch

import requests

from odoo.tests import tagged
from odoo.tests.common import HttpCase
from odoo.tools import mute_logger

from .common import LlmsTxtCommon
from odoo.addons.muk_website_llms_txt.models import ir_http as ir_http_model


@tagged('post_install', '-at_install')
class TestLlmsTxtMarkdownNegotiation(LlmsTxtCommon, HttpCase):
    """Test the ``Accept: text/markdown`` content negotiation on website pages."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.website = cls._setup_llms_website()
        cls.page = cls._create_page(
            'Llms Markdown Page',
            '/llms-markdown-page',
            'LLMS_MARKDOWN_BODY_MARKER',
        )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _open_markdown(self, path: str = '/llms-markdown-page') -> requests.Response:
        """Request the given path asking for markdown."""
        return self.url_open(path, headers={'Accept': 'text/markdown'})

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_markdown_is_served_for_an_html_page(self):
        response = self._open_markdown()
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/markdown', response.headers['Content-Type'])
        self.assertIn('LLMS_MARKDOWN_BODY_MARKER', response.text)
        self.assertNotIn('<div>', response.text)

    def test_markdown_response_reports_its_token_estimate(self):
        response = self._open_markdown()
        self.assertGreater(int(response.headers['x-markdown-tokens']), 0)

    def test_markdown_response_varies_on_accept(self):
        response = self._open_markdown()
        self.assertIn('Accept', response.headers['Vary'])

    def test_markdown_response_carries_the_content_signal(self):
        self.website.llms_content_signal = 'none'
        response = self._open_markdown()
        self.assertEqual(
            response.headers['Content-Signal'], 'ai-train=no, search=no, ai-input=no'
        )
        self.website.llms_content_signal = 'all'
        response = self._open_markdown()
        self.assertEqual(
            response.headers['Content-Signal'], 'ai-train=yes, search=yes, ai-input=yes'
        )

    def test_html_is_served_when_markdown_is_not_requested(self):
        response = self.url_open('/llms-markdown-page')
        self.assertIn('text/html', response.headers['Content-Type'])
        self.assertNotIn('x-markdown-tokens', response.headers)
        self.assertIn('<', response.text)

    def test_a_plain_text_document_is_never_rewritten(self):
        response = self._open_markdown('/llms.txt')
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/plain', response.headers['Content-Type'])
        self.assertTrue(response.text.startswith('#'))

    def test_a_missing_page_is_never_rewritten(self):
        response = self._open_markdown('/llms-markdown-does-not-exist')
        self.assertEqual(response.status_code, 404)
        self.assertNotIn('text/markdown', response.headers.get('Content-Type', ''))
        self.assertNotIn('x-markdown-tokens', response.headers)

    @mute_logger('odoo.addons.muk_website_llms_txt.models.ir_http')
    def test_a_failing_conversion_keeps_serving_the_html_page(self):
        with patch.object(
            ir_http_model,
            'page_to_agent_markdown',
            side_effect=ValueError('boom'),
        ):
            response = self._open_markdown()
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/html', response.headers['Content-Type'])
        self.assertIn('LLMS_MARKDOWN_BODY_MARKER', response.text)

    def test_an_empty_conversion_keeps_serving_the_html_page(self):
        with patch.object(ir_http_model, 'page_to_agent_markdown', return_value=''):
            response = self._open_markdown()
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/html', response.headers['Content-Type'])
        self.assertNotIn('x-markdown-tokens', response.headers)
