from __future__ import annotations

from typing import Any

from odoo.http import request

from odoo.addons.muk_mcp.controllers.mcp import MCPController


class MCPController(MCPController):
    """Tell the tools whether the client can ask the user, and what was answered."""

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _get_elicitation(self, params: dict[str, Any]) -> dict[str, Any]:
        """Describe what the client declared and answered about questions."""
        declared = (self._get_client_capabilities(params) or {}).get('elicitation')
        responses = params.get('inputResponses')
        response = responses.get('confirm') if isinstance(responses, dict) else None
        return {
            'stateless': request._mcp_profile.stateless,
            'supported': isinstance(declared, dict)
            and (not declared or 'form' in declared),
            'principal': str(self._get_request_rate_limiter()),
            'state': params.get('requestState'),
            'action': response.get('action') if isinstance(response, dict) else None,
        }

    def _handle_tools_call(self, params: dict[str, Any]) -> dict[str, Any]:
        """Hand the elicitation of the request to the tool that runs."""
        request.update_context(mcp_elicitation=self._get_elicitation(params))
        return super()._handle_tools_call(params)
