from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    """Add the check options to the general settings."""

    _inherit = 'res.config.settings'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    check_online = fields.Boolean(
        string='Online Checks',
        config_parameter='muk_check.online',
        default=True,
    )

    check_notifications = fields.Boolean(
        string='Notifications',
        config_parameter='muk_check.notifications',
        default=True,
    )
