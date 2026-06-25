from __future__ import annotations

import re

import werkzeug

from odoo import SUPERUSER_ID, api, models
from odoo.http import Response, request
from odoo.tools.misc import str2bool


class IrHttp(models.AbstractModel):
    """Add the ``mcp`` auth method and JSON-RPC error rendering."""

    _inherit = 'ir.http'

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @classmethod
    def _auth_method_mcp(cls) -> None:
        """Authenticate the request from its bearer token and switch user.

        :raise werkzeug.exceptions.Unauthorized: when the token is missing
            or does not match an active key
        """
        if request.httprequest.method != 'OPTIONS':
            env = api.Environment(request.env.cr, SUPERUSER_ID, {})
            header = request.httprequest.headers.get('Authorization', '')
            match = re.match(r'^bearer\s+(.+)$', header, re.IGNORECASE)
            if not (token := match and match.group(1).strip()):
                raise werkzeug.exceptions.Unauthorized()
            if not (mcp_key := env['muk_mcp.key'].authenticate(token)):
                raise werkzeug.exceptions.Unauthorized()
            request.update_env(user=mcp_key.user_id.id)
            annotate = env['ir.config_parameter'].get_param(
                'muk_mcp.annotate_messages',
                'True',
            )
            request._mcp_key = mcp_key
            if str2bool(annotate, default=True):
                request.update_env(
                    context={
                        'mcp_name': mcp_key.name,
                    },
                )
            request.session.can_save = False
        return

    @classmethod
    def _handle_error(cls, exception: Exception) -> Response:
        """Render MCP-routed HTTP errors as JSON-RPC error responses."""
        if (
            getattr(request, 'dispatcher', None)
            and request.dispatcher.routing_type == 'mcp'
        ):
            if (
                isinstance(exception, werkzeug.exceptions.HTTPException)
                and (exception.code or 0) >= 400
            ):
                return request.make_json_response(
                    {
                        'jsonrpc': '2.0',
                        'id': None,
                        'error': {
                            'code': -32603,
                            'message': str(exception),
                        },
                    },
                    status=exception.code,
                )
        return super()._handle_error(exception)
