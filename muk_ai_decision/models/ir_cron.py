from __future__ import annotations

from odoo import api, models


class IrCron(models.Model):
    """Switch an AI scheduled action between its AI steps."""

    _inherit = 'ir.cron'

    # ----------------------------------------------------------
    # Compute
    # ----------------------------------------------------------

    @api.onchange('ai_step')
    def _onchange_ai_step(self) -> None:
        """Switch the type of the scheduled action to the chosen AI step."""
        self.state = self.ai_step
