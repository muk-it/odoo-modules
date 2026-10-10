from __future__ import annotations

import re

import werkzeug
from werkzeug.datastructures import WWWAuthenticate
from werkzeug.exceptions import Unauthorized

from odoo import SUPERUSER_ID, api, models
from odoo.http import Response, request
from odoo.tools.misc import str2bool


class IrHttp(models.AbstractModel):
    """Add the ``mcp`` bearer auth method and JSON-RPC error rendering."""

    _inherit = 'ir.http'

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @classmethod
    def _get_mcp_challenge(cls, token: str | None) -> WWWAuthenticate:
        """Return the ``WWW-Authenticate`` challenge of a rejected MCP request."""
        return WWWAuthenticate('bearer')

    @classmethod
    def _authenticate_mcp_token(cls, token: str) -> str | None:
        """Switch the request to the user of the MCP key ``token``.

        :return: the key's name, or ``None`` when no active key matches
        """
        env = api.Environment(request.env.cr, SUPERUSER_ID, {})
        if not (key := env['muk_mcp.key'].authenticate(token)):
            return None
        request.update_env(user=key.user_id.id)
        request._mcp_key = key
        return key.name

    @classmethod
    def _auth_method_mcp(cls) -> None:
        """Authenticate the request from its bearer token.

        :raise werkzeug.exceptions.Unauthorized: when the bearer token is missing
            or matches no credential
        """
        if request.httprequest.method == 'OPTIONS':
            return
        header = request.httprequest.headers.get('Authorization', '')
        match = re.match(r'^bearer\s+(.+)$', header, re.IGNORECASE)
        token = match and match.group(1).strip()
        if not (name := token and cls._authenticate_mcp_token(token)):
            raise Unauthorized(www_authenticate=cls._get_mcp_challenge(token))
        annotate = (
            request.env['ir.config_parameter']
            .sudo()
            .get_param('muk_mcp.annotate_messages', 'True')
        )
        if str2bool(annotate, default=True):
            request.update_env(context={'mcp_name': name})
        request.session.can_save = False

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
                    headers=[
                        header
                        for header in exception.get_headers()
                        if header[0] == 'WWW-Authenticate'
                    ],
                    status=exception.code,
                )
        return super()._handle_error(exception)
