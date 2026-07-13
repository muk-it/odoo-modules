from __future__ import annotations

from odoo import models


class IrHttp(models.AbstractModel):
    """Expose the company background-image flag through the session info."""

    _inherit = 'ir.http'

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    def session_info(self) -> dict:
        """Add a ``has_background_image`` flag to each allowed company."""
        result = super().session_info()
        if self.env.user._is_internal():
            allowed = result['user_companies']['allowed_companies']
            for company in self.env.user.company_ids.with_context(bin_size=True):
                if entry := allowed.get(company.id):
                    entry.update(
                        {
                            'has_background_image': bool(company.background_image),
                        }
                    )
        return result
