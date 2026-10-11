from __future__ import annotations

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    """Expose the MuK AI Automation extension toggle in the settings."""

    _inherit = 'res.config.settings'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    module_muk_ai_automation = fields.Boolean(
        string='MuK AI Automation',
        help='Run AI agents as server actions and automation rule steps.',
    )
