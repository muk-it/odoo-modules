from __future__ import annotations

from odoo import fields, models


class IrActionsServer(models.Model):
    """Add batch-execution settings to server actions."""

    _inherit = 'ir.actions.server'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    execute_in_batch = fields.Boolean(
        string='Execute in Batch',
        help=(
            'Run the action from the "Actions" menu in batches of the given size, '
            'one request per batch, with a progress bar. Such actions should not '
            'return an action to open.'
        ),
    )

    execution_batch_size = fields.Integer(
        string='Batch Size',
        default=100,
    )
