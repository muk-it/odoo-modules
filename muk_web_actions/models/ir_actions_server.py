from __future__ import annotations

from odoo import api, fields, models


class IrActionsServer(models.Model):
    """Add batch-execution settings to server actions."""

    _inherit = 'ir.actions.server'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    execute_in_batch = fields.Boolean(
        string='Execute in Batch',
        help=(
            'If this flag is active the actions are executed in batch. '
            'Note that such actions should not set the action variable.'
        ),
        default=False,
    )

    execution_batch_size = fields.Integer(
        string='Exectution Batch Size',
        default=100,
    )

    # ----------------------------------------------------------
    # ORM
    # ----------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list: list[dict]) -> IrActionsServer:
        """Create actions and clear the registry cache for new bindings."""
        res = super().create(vals_list)
        self.env.registry.clear_cache()
        return res

    def write(self, vals: dict) -> bool:
        """Write actions and clear the registry cache for changed bindings."""
        res = super().write(vals)
        self.env.registry.clear_cache()
        return res
