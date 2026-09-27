from __future__ import annotations

from odoo import models


class IrHttp(models.AbstractModel):
    """Expose appbar image availability per company in the session info."""

    _inherit = 'ir.http'

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    def session_info(self) -> dict:
        """Flag companies that carry an appbar footer image."""
        result = super().session_info()
        if self.env.user._is_internal():
            allowed = result['user_companies']['allowed_companies']
            for company in self.env['res.company'].browse(allowed):
                allowed[company.id]['has_appsbar_image'] = bool(company.appbar_image)
        return result
