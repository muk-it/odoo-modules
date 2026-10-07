from __future__ import annotations

from odoo import models


class IrHttp(models.AbstractModel):
    """Expose the preview settings in the session info."""

    _inherit = 'ir.http'

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    def session_info(self) -> dict:
        """Add the Office preview and report tab flags to the session info."""
        result = super().session_info()
        params = self.env['ir.config_parameter'].sudo()
        result['preview_office_enabled'] = params.get_bool(
            'muk_web_preview.office_enabled'
        )
        result['preview_report_open'] = params.get_bool('muk_web_preview.report_open')
        return result
