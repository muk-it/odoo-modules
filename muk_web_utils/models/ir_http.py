from __future__ import annotations

from odoo import models
from odoo.tools import str2bool


class IrHttp(models.AbstractModel):
    """Expose the quick-create toggle through the web session info."""

    _inherit = 'ir.http'

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    def session_info(self) -> dict:
        """Add the ``disable_quick_create`` flag to the session payload."""
        result = super().session_info()
        result['disable_quick_create'] = str2bool(
            self.env['ir.config_parameter']
            .sudo()
            .get_param(
                'muk_web_utils.disable_quick_create',
                default='',
            ),
            default=False,
        )
        return result
