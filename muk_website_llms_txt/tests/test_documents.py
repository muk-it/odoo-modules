from __future__ import annotations

from unittest.mock import patch

from odoo import models
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.muk_website_llms_txt.models import website as website_model
from odoo.addons.muk_website_llms_txt.tools.constants import LLMS_DOCUMENT_PREFIX


@tagged('post_install', '-at_install')
class TestLlmsTxtDocuments(TransactionCase):
    """Test the stored documents backing the llms.txt routes."""

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
                'llms_include_pages': True,
            }
        )
        cls.cron = cls.env.ref('muk_website_llms_txt.ir_cron_generate_llms_documents')

    @classmethod
    def _create_page(cls, name: str, url: str, marker: str) -> models.Model:
        """Create a published website page carrying a unique text marker.

        :param name: the display name of the page
        :param url: the page URL, used as the view key suffix as well
        :param marker: a unique text marker embedded in the page content
        :return: the created ``website.page`` record
        """
        key = f'muk_website_llms_txt.test{url.replace("-", "_").replace("/", "_")}'
        return cls.env['website.page'].create(
            {
                'name': name,
                'url': url,
                'type': 'qweb',
                'key': key,
                'arch': f'<t t-name="{key}"><div>{marker}</div></t>',
                'website_id': cls.website.id,
                'is_published': True,
            }
        )

    def _run_cron(self) -> None:
        """Run the document cron with its per-document commit neutralized."""
        with patch.object(self.env.cr, 'commit', lambda: None):
            self.env['website']._cron_generate_llms_documents()

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

    def test_document_is_stored_in_an_attachment(self):
        attachment = self.website._get_llms_document('llms.txt')
        self.assertEqual(attachment.name, f'{LLMS_DOCUMENT_PREFIX}llms.txt')
        self.assertEqual(attachment.mimetype, 'text/plain')
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

    def test_cron_rebuilds_the_documents_in_place(self):
        attachment = self.website._get_llms_document('llms.txt')
        self._create_page('Llms Cron Page', '/llms-doc-cron', 'LLMS_CRON_MARKER')
        self._run_cron()
        self.assertEqual(self.website._search_llms_document('llms.txt'), attachment)
        self.assertIn('/llms-doc-cron', attachment.raw.decode())

    def test_cron_drops_the_documents_of_disabled_routes(self):
        self.website._get_llms_document('llms.txt')
        self.website._get_llms_document('llms-full.txt')
        self.website.llms_full_txt_enabled = False
        self._run_cron()
        stored = self._stored_documents()
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored.name, f'{LLMS_DOCUMENT_PREFIX}llms.txt')

    def test_configuration_change_schedules_a_rebuild(self):
        attachment = self.website._get_llms_document('llms.txt')
        self.env['ir.cron.trigger'].search([('cron_id', '=', self.cron.id)]).unlink()
        self.website.llms_include_pages = False
        self.assertTrue(
            self.env['ir.cron.trigger'].search_count([('cron_id', '=', self.cron.id)])
        )
        self.assertTrue(attachment.exists())

    def test_unrelated_change_schedules_nothing(self):
        self.env['ir.cron.trigger'].search([('cron_id', '=', self.cron.id)]).unlink()
        self.website.llms_content_signal = 'none'
        self.assertFalse(
            self.env['ir.cron.trigger'].search_count([('cron_id', '=', self.cron.id)])
        )

    def test_every_record_is_listed_across_batches(self):
        urls = [f'/llms-doc-batch-{index}' for index in range(5)]
        for index, url in enumerate(urls):
            self._create_page(f'Llms Batch Page {index}', url, f'LLMS_BATCH_{index}')
        with patch.object(website_model, 'LLMS_BATCH_SIZE', 2):
            content = self.website._generate_llms_document('llms.txt').raw.decode()
        for url in urls:
            self.assertIn(url, content)
