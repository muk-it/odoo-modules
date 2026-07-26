from __future__ import annotations

from odoo import fields, models


class IrModel(models.Model):
    """Flag models whose creation is sensitive and needs AI approval."""

    _inherit = 'ir.model'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    ai_sensitive = fields.Boolean(
        string='Sensitive for AI',
        help=(
            'Creates on this model trigger an approval prompt for AI '
            'agents, regardless of which fields are written.'
        ),
        default=False,
    )
