from __future__ import annotations

from unittest.mock import patch

from odoo import models
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from .common import LlmsTxtCommon
from odoo.addons.muk_website_llms_txt.models import website as website_model
from odoo.addons.muk_website_llms_txt.tools.constants import LLMS_DOCUMENT_PREFIX


@tagged('post_install', '-at_install')
class TestLlmsTxtDocuments(LlmsTxtCommon, TransactionCase):
    """Test the stored attachments backing the llms.txt routes."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.website = cls._setup_llms_website()

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _stored_documents(self) -> models.Model:
        """Return the attachments storing this website's documents."""
        return self.env['ir.attachment'].search(
            [
                ('name', '=like', f'{LLMS_DOCUMENT_PREFIX}%'),
                ('res_model', '=', 'website'),
                ('res_id', '=', self.website.id),
            ]
        )

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_document_is_stored_as_a_public_text_attachment(self):
        attachment = self.website._get_llms_document('llms.txt')
        self.assertEqual(attachment.name, f'{LLMS_DOCUMENT_PREFIX}llms.txt')
        self.assertEqual(attachment.mimetype, 'text/plain')
        self.assertEqual(attachment.res_model, 'website')
        self.assertEqual(attachment.res_id, self.website.id)
        self.assertTrue(attachment.public)
        self.assertTrue(attachment.raw.decode().startswith('#'))
        self.assertGreater(int(attachment.description), 0)

    def test_document_is_reused_without_rebuilding(self):
        first = self.website._get_llms_document('llms.txt')
        self._create_page('Llms Reuse Page', '/llms-doc-reuse', 'LLMS_REUSE_MARKER')
        second = self.website._get_llms_document('llms.txt')
        self.assertEqual(first, second)
        self.assertNotIn('/llms-doc-reuse', second.raw.decode())

    def test_documents_are_stored_separately(self):
        self.website._get_llms_document('llms.txt')
        self.website._get_llms_document('llms-full.txt')
        self.assertEqual(len(self._stored_documents()), 2)

    def test_regenerating_replaces_the_stored_copy_in_place(self):
        first = self.website._generate_llms_document('llms.txt')
        self._create_page('Llms Again Page', '/llms-doc-again', 'LLMS_AGAIN_MARKER')
        second = self.website._generate_llms_document('llms.txt')
        self.assertEqual(first, second)
        self.assertEqual(len(self._stored_documents()), 1)
        self.assertIn('/llms-doc-again', second.raw.decode())

    def test_index_lists_the_page_url_and_name(self):
        self._create_page('Llms Index Page', '/llms-doc-index', 'LLMS_INDEX_MARKER')
        content = self.website._generate_llms_document('llms.txt').raw.decode()
        base_url = self.website._get_llms_base_url()
        self.assertIn('## Pages', content)
        self.assertIn(f'- [Llms Index Page]({base_url}/llms-doc-index)', content)
        self.assertNotIn('LLMS_INDEX_MARKER', content)

    def test_full_document_carries_the_page_markdown(self):
        self._create_page('Llms Body Page', '/llms-doc-body', 'LLMS_BODY_MARKER')
        content = self.website._generate_llms_document('llms-full.txt').raw.decode()
        self.assertIn('## Llms Body Page', content)
        self.assertIn('LLMS_BODY_MARKER', content)

    def test_disabling_pages_empties_the_page_section(self):
        self._create_page('Llms Off Page', '/llms-doc-off', 'LLMS_OFF_MARKER')
        self.website.llms_include_pages = False
        content = self.website._generate_llms_document('llms.txt').raw.decode()
        self.assertNotIn('## Pages', content)
        self.assertNotIn('/llms-doc-off', content)

    def test_every_record_is_listed_across_batches(self):
        urls = [f'/llms-doc-batch-{index}' for index in range(5)]
        for index, url in enumerate(urls):
            self._create_page(f'Llms Batch Page {index}', url, f'LLMS_BATCH_{index}')
        with patch.object(website_model, 'LLMS_BATCH_SIZE', 2):
            content = self.website._generate_llms_document('llms.txt').raw.decode()
        for url in urls:
            self.assertIn(url, content)

    def test_base_url_falls_back_to_the_system_parameter(self):
        self.website.domain = False
        expected = (
            self.env['ir.config_parameter'].sudo().get_param('web.base.url', '')
        ).rstrip('/')
        self.assertEqual(self.website._get_llms_base_url(), expected)
        self.website.domain = 'https://llms.example.test/'
        self.assertEqual(self.website._get_llms_base_url(), 'https://llms.example.test')
