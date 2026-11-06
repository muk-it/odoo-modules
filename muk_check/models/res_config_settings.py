from __future__ import annotations

from odoo import fields, models


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
    # ORM
    # ----------------------------------------------------------

    def get_values(self) -> dict:
        """Read the options, which are on unless they were turned off."""
        parameters = self.env['ir.config_parameter'].sudo()
        return {
            **super().get_values(),
            'check_online': parameters.get_param('muk_check.online', 'True') == 'True',
            'check_notifications': (
                parameters.get_param('muk_check.notifications', 'True') == 'True'
            ),
        }

    def set_values(self) -> None:
        """Store the options as text, because core deletes a false parameter."""
        super().set_values()
        parameters = self.env['ir.config_parameter'].sudo()
        parameters.set_param('muk_check.online', str(self.check_online))
        parameters.set_param('muk_check.notifications', str(self.check_notifications))
