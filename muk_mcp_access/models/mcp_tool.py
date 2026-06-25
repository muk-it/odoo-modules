from __future__ import annotations

from typing import Any

from odoo import api, models
from odoo.api import Environment
from odoo.http import request

from odoo.addons.muk_mcp.core.tool import get_tool_index


class MCPTool(models.Model):
    """Track the current tool category on the request for access enforcement."""

    _inherit = 'muk_mcp.tool'

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _call(
        self,
        name: str,
        arguments: dict[str, Any] | None,
        env: Environment,
        enforce_scope: str | None = None,
    ) -> tuple[Any, dict[str, Any]]:
        """Stash the tool's category on the request, then clear it after the call."""
        entry = get_tool_index(env).get(name)
        if entry and request:
            request._mcp_tool_category = entry.get('category', 'read')
        try:
            return super()._call(name, arguments, env, enforce_scope)
        finally:
            if request:
                request._mcp_tool_category = None
