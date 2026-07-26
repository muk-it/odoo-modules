from __future__ import annotations

from unittest.mock import patch

from odoo import models
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from .common import LlmsTxtCommon
from odoo.addons.muk_website_llms_txt.tools.constants import LLMS_DOCUMENT_PREFIX


@tagged('post_install', '-at_install')
class TestLlmsTxtDocumentCron(LlmsTxtCommon, TransactionCase):
    """Test the cron that rebuilds the stored llms.txt documents."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.website = cls._setup_llms_website()
        cls.cron = cls._setup_llms_cron()

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @classmethod
    def _setup_llms_cron(cls) -> models.Model:
        """Return the document cron, activated for the scheduling tests.

        ``_trigger`` silently drops the run it should queue when the cron is
        inactive, and neutralized databases deactivate every cron. The
        fixture owns the flag so the tests assert what the code schedules
        instead of what the database was restored with.
        """
        cron = cls.env.ref('muk_website_llms_txt.ir_cron_generate_llms_documents')
        cron.active = True
        return cron

    def _run_cron(self) -> int:
        """Run the document cron and return how often it committed.

        The cron commits after every document so a run cut short keeps what it
        already rebuilt. The commit is counted instead of executed, because a
        real commit would escape the test transaction.
        """
        commits = 0

        def _commit() -> None:
            nonlocal commits
            commits += 1

        with patch.object(self.env.cr, 'commit', _commit):
            self.env['website']._cron_generate_llms_documents()
        return commits

    def _stored(self, website: models.Model) -> models.Model:
        """Return the attachments storing the documents of the given website."""
        return self.env['ir.attachment'].search(
            [
                ('name', '=like', f'{LLMS_DOCUMENT_PREFIX}%'),
                ('res_model', '=', 'website'),
                ('res_id', '=', website.id),
            ]
        )

    def _pending_triggers(self) -> int:
        """Return the number of queued triggers for the document cron."""
        return self.env['ir.cron.trigger'].search_count(
            [('cron_id', '=', self.cron.id)]
        )

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_cron_rebuilds_the_document_in_place(self):
        attachment = self.website._get_llms_document('llms.txt')
        self._create_page('Llms Cron Page', '/llms-cron-page', 'LLMS_CRON_MARKER')
        self._run_cron()
        self.assertEqual(self.website._search_llms_document('llms.txt'), attachment)
        self.assertIn('/llms-cron-page', attachment.raw.decode())

    def test_cron_commits_after_every_document(self):
        websites = self.env['website'].search([])
        self.assertEqual(self._run_cron(), len(websites) * 2)

    def test_cron_refreshes_the_token_estimate(self):
        attachment = self.website._get_llms_document('llms.txt')
        before = int(attachment.description)
        self._create_page('Llms Token Page', '/llms-cron-token', 'LLMS_TOKEN_MARKER')
        self._run_cron()
        self.assertGreater(int(attachment.description), before)

    def test_cron_changes_the_checksum_so_caches_revalidate(self):
        attachment = self.website._get_llms_document('llms.txt')
        before = attachment.checksum
        self._create_page('Llms Etag Page', '/llms-cron-etag', 'LLMS_ETAG_MARKER')
        self._run_cron()
        self.assertNotEqual(attachment.checksum, before)

    def test_cron_drops_the_document_of_a_disabled_route(self):
        self.website._get_llms_document('llms.txt')
        self.website._get_llms_document('llms-full.txt')
        self.website.llms_full_txt_enabled = False
        self._run_cron()
        stored = self._stored(self.website)
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored.name, f'{LLMS_DOCUMENT_PREFIX}llms.txt')

    def test_cron_rebuilds_every_website(self):
        other = self.env['website'].create(
            {
                'name': 'Llms Second Website',
                'llms_txt_enabled': True,
                'llms_full_txt_enabled': True,
            }
        )
        self._run_cron()
        self.assertEqual(len(self._stored(self.website)), 2)
        self.assertEqual(len(self._stored(other)), 2)
        self.assertIn('Llms Second Website', self._stored(other)[0].raw.decode())

    def test_a_failing_render_keeps_the_previous_document_serving(self):
        attachment = self.website._get_llms_document('llms.txt')
        previous = attachment.raw
        self._create_page('Llms Fail Page', '/llms-cron-fail', 'LLMS_FAIL_MARKER')
        with (
            patch.object(
                type(self.website),
                '_build_llms_txt_content',
                side_effect=ValueError('boom'),
            ),
            self.assertRaises(ValueError),
        ):
            self._run_cron()
        self.assertEqual(attachment.raw, previous)
        self.assertNotIn('/llms-cron-fail', previous.decode())

    def test_saving_the_settings_schedules_a_rebuild(self):
        self.env['ir.cron.trigger'].search([('cron_id', '=', self.cron.id)]).unlink()
        settings = self.env['res.config.settings'].create(
            {'website_id': self.website.id, 'llms_include_pages': False}
        )
        settings.execute()
        self.assertFalse(self.website.llms_include_pages)
        self.assertTrue(self._pending_triggers())

    def test_a_configuration_change_schedules_a_rebuild(self):
        attachment = self.website._get_llms_document('llms.txt')
        self.env['ir.cron.trigger'].search([('cron_id', '=', self.cron.id)]).unlink()
        self.website.llms_include_pages = False
        self.assertTrue(self._pending_triggers())
        self.assertTrue(attachment.exists())

    def test_an_unrelated_change_schedules_nothing(self):
        self.env['ir.cron.trigger'].search([('cron_id', '=', self.cron.id)]).unlink()
        self.website.llms_content_signal = 'none'
        self.website.llms_link_headers_enabled = False
        self.assertFalse(self._pending_triggers())
