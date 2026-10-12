from __future__ import annotations

from odoo import api, fields, models


class BaseAutomation(models.Model):
    """Offer the AI steps as the type of an AI automation rule."""

    _inherit = 'base.automation'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    allowed_states = fields.Json(
        compute='_compute_allowed_states',
    )

    # ----------------------------------------------------------
    # Compute
    # ----------------------------------------------------------

    @api.depends('state')
    @api.depends_context('ai_steps')
    def _compute_allowed_states(self) -> None:
        """Offer the types its server action offers, also on a new rule."""
        self.allowed_states = self.env['ir.actions.server'].new({}).allowed_states
