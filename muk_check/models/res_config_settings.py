from __future__ import annotations

from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    """Add the check options to the general settings."""

    _inherit = 'res.config.settings'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    check_online = fields.Boolean(
        string='Online Checks',
    )

    check_notifications = fields.Boolean(
        string='Notifications',
    )

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    def get_values(self) -> dict:
        """Read the options, which are on until they are turned off."""
        values = super().get_values()
        parameters = self.env['ir.config_parameter'].sudo()
        values.update(
            check_online=parameters.get_param('muk_check.online') != 'False',
            check_notifications=(
                parameters.get_param('muk_check.notifications') != 'False'
            ),
        )
        return values

    def set_values(self) -> None:
        """Store the options as text, because a removed parameter means on."""
        super().set_values()
        parameters = self.env['ir.config_parameter'].sudo()
        parameters.set_param('muk_check.online', str(self.check_online))
        parameters.set_param('muk_check.notifications', str(self.check_notifications))
