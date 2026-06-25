from __future__ import annotations

from typing import Any

from odoo import api, models


class MCPMixin(models.AbstractModel):
    """Filter the MCP model listing down to the access allowlist."""

    _inherit = 'muk_mcp.mixin'

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    def _mcp_list_models(
        self, search: str = '', limit: int = 100
    ) -> list[dict[str, Any]]:
        """Drop models absent from the access allowlist when one is active."""
        result = super()._mcp_list_models(search=search, limit=limit)
        allowed = self.env['muk_mcp_access.model']._get_allowed_model_names()
        if allowed is not None:
            result = [m for m in result if m['model'] in allowed]
        return result
