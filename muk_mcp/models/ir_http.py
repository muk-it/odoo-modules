from __future__ import annotations

import re
from typing import Any

from werkzeug.datastructures import WWWAuthenticate
from werkzeug.exceptions import HTTPException, Unauthorized
from werkzeug.routing import Rule

from odoo import models
from odoo.http import request

from odoo.addons.muk_mcp.tools.common import MCP_CORS_REQUEST_HEADERS, MCP_ENDPOINT


class IrHttp(models.AbstractModel):
    """Add the ``mcp`` bearer auth method and the MCP CORS preflight headers."""

    _inherit = 'ir.http'

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @classmethod
    def _auth_method_mcp(cls, routing: dict[str, Any]) -> None:
        """Authenticate the request from its MCP key and switch to the key's user.

        :raise werkzeug.exceptions.Unauthorized: when the bearer token is missing
            or does not match an active key
        """
        header = request.httprequest.headers.get('Authorization', '')
        match = re.match(r'^bearer\s+(.+)$', header, re.IGNORECASE)
        token = match and match.group(1).strip()
        key = token and request.env['muk_mcp.key'].sudo().authenticate(token)
        if not key:
            raise Unauthorized(www_authenticate=WWWAuthenticate('bearer'))
        request.update_env(user=key.user_id.id)
        request._mcp_key = key
        if (
            request.env['ir.config_parameter']
            .sudo()
            .get_bool(
                'muk_mcp.annotate_messages',
                True,
            )
        ):
            request.update_context(mcp_name=key.name)
        request.session.can_save = False

    @classmethod
    def _pre_dispatch(cls, rule: Rule, args: dict[str, Any]) -> None:
        """Allow the MCP transport headers on the endpoint's CORS preflight."""
        try:
            super()._pre_dispatch(rule, args)
        except HTTPException:
            if request.httprequest.path == MCP_ENDPOINT:
                request.future_response.headers.set(
                    'Access-Control-Allow-Headers',
                    MCP_CORS_REQUEST_HEADERS,
                )
            raise
