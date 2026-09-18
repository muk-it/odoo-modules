from __future__ import annotations

from odoo import models
from odoo.exceptions import UserError


class AISessionToolContext(models.AbstractModel):
    """Resolve the AI session an MCP tool call is running inside."""

    _inherit = 'muk_mcp.mixin'

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _resolve_mcp_session(self, outside: str) -> models.Model:
        """Return the AI session bound to the current MCP context.

        :param outside: what to tell the model when there is no session
        :return: the session, empty when it no longer exists
        :raise UserError: when invoked outside an AI session
        """
        if not (session_id := self.env.context.get('muk_mcp_session_id')):
            raise UserError(outside)
        return self.env['muk_ai.session'].browse(session_id).exists()
