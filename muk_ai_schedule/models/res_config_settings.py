from __future__ import annotations

from odoo import fields, models

from odoo.addons.muk_ai_schedule.tools.constants import DEFAULT_MAX_WAITS


class ResConfigSettings(models.TransientModel):
    """Expose how often a chat may wait in the AI settings."""

    _inherit = 'res.config.settings'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    ai_max_waits = fields.Integer(
        string='Max Waits',
        help='How many times one chat may pause itself to wait before it has to finish.',
        config_parameter='muk_ai_schedule.max_waits',
        default=DEFAULT_MAX_WAITS,
    )
