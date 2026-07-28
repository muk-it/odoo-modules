from __future__ import annotations

from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestIrActionsReport(TransactionCase):
    """Cover the batch execution flag on report actions."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.report_model = cls.env['ir.actions.report']

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _create_report(self, report_type: str, execute_in_batch: bool) -> object:
        """Create a report action of the given type and batch setting."""
        return self.report_model.create(
            {
                'name': f'Report {report_type}',
                'model': 'res.partner',
                'report_name': f'muk_web_actions.report_{report_type}',
                'report_type': report_type,
                'execute_in_batch': execute_in_batch,
            }
        )

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_pdf_report_keeps_the_batch_flag(self):
        report = self._create_report('qweb-pdf', True)
        self.assertTrue(report.execute_in_batch)

    def test_html_report_is_not_batched_by_default(self):
        report = self._create_report('qweb-html', False)
        self.assertFalse(report.execute_in_batch)

    def test_switching_a_report_to_html_clears_the_batch_flag(self):
        report = self._create_report('qweb-pdf', True)
        self.assertTrue(report.execute_in_batch)
        report.report_type = 'qweb-html'
        self.assertFalse(report.execute_in_batch)

    def test_switching_a_report_back_to_pdf_keeps_it_unbatched(self):
        report = self._create_report('qweb-pdf', True)
        report.report_type = 'qweb-html'
        self.assertFalse(report.execute_in_batch)
        report.report_type = 'qweb-pdf'
        self.assertFalse(report.execute_in_batch)

    def test_batch_flag_can_be_set_again_on_a_pdf_report(self):
        report = self._create_report('qweb-pdf', True)
        report.report_type = 'qweb-html'
        self.assertFalse(report.execute_in_batch)
        report.write({'report_type': 'qweb-pdf', 'execute_in_batch': True})
        self.assertTrue(report.execute_in_batch)
