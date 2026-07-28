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
            'If this flag is active, the reports are generated and '
            'downloaded one by one.'
        ),
        readonly=False,
        default=False,
        store=True,
    )

    # ----------------------------------------------------------
    # Compute
    # ----------------------------------------------------------

    @api.depends('report_type')
    def _compute_execute_in_batch(self) -> None:
        """Disable batch execution for HTML reports."""
        for record in self:
            if record.report_type == 'qweb-html':
                record.execute_in_batch = False

    # ----------------------------------------------------------
    # ORM
    # ----------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list: list[dict]) -> IrActionsReport:
        """Create reports and clear the registry cache for new bindings."""
        res = super().create(vals_list)
        self.env.registry.clear_cache()
        return res

    def write(self, vals: dict) -> bool:
        """Write reports and clear the registry cache for changed bindings."""
        res = super().write(vals)
        self.env.registry.clear_cache()
        return res
