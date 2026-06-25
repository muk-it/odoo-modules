from __future__ import annotations

from odoo import models
from odoo.tools import str2bool


class IrHttp(models.AbstractModel):
    """Expose the Office preview toggle in the session info."""

    _inherit = 'ir.http'

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    def session_info(self) -> dict:
        """Add the Office preview enabled flag to the session info."""
        result = super().session_info()
        result['preview_office_enabled'] = str2bool(
            self.env['ir.config_parameter']
            .sudo()
            .get_param(
                'muk_web_preview.office_enabled',
                default='',
            ),
            default=False,
        )
        return result
