from __future__ import annotations

from odoo import models


class IrHttp(models.AbstractModel):
    """Expose the Office preview toggle in the session info."""

    _inherit = 'ir.http'

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    def session_info(self) -> dict:
        """Add the Office preview flag to the session info."""
        result = super().session_info()
        result['preview_office_enabled'] = (
            self.env['ir.config_parameter']
            .sudo()
            .get_bool('muk_web_preview.office_enabled')
        )
        return result
