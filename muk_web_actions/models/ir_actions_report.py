from __future__ import annotations

from odoo import api, fields, models


class IrActionsReport(models.Model):
    """Add a batch-execution flag to report actions."""

    _inherit = 'ir.actions.report'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    execute_in_batch = fields.Boolean(
        compute='_compute_execute_in_batch',
        string='Execute in Batch',
        help=(
            'Print the report from the "Print" menu one record at a time, '
            'with one file per record and a progress bar.'
        ),
        readonly=False,
        store=True,
    )

    # ----------------------------------------------------------
    # Compute
    # ----------------------------------------------------------

    @api.depends('report_type')
    def _compute_execute_in_batch(self) -> None:
        """Disable batch execution for HTML reports."""
        self.filtered(lambda r: r.report_type == 'qweb-html').execute_in_batch = False
