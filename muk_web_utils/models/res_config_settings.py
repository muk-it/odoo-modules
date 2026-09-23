from __future__ import annotations

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    """Add the Many2one quick-create toggle to the general settings."""

    _inherit = 'res.config.settings'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    disable_many2one_quick_create = fields.Boolean(
        config_parameter='muk_web_utils.disable_quick_create',
        string='Disable Quick Create for Many2one Fields',
    )
