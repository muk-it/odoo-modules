from __future__ import annotations

from odoo import api, models


class MCPMixin(models.AbstractModel):
    """Filter the MCP model listing down to the access allowlist."""

    _inherit = 'muk_mcp.mixin'

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _mcp_listable_model_names(self) -> set[str] | None:
        """Restrict the MCP model listing to the read allowlist when one is active."""
        return self.env['muk_mcp_access.model']._get_allowed_model_names('read')
