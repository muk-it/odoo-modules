from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import werkzeug
from werkzeug.exceptions import HTTPException
from werkzeug.routing import Rule

from odoo import http
from odoo.http import CORS_MAX_AGE, Request, Response

from odoo.addons.muk_mcp.tools.common import (
    MCP_CORS_REQUEST_HEADERS,
    MCP_CORS_RESPONSE_HEADERS,
)


class MCPDispatcher(http.Dispatcher):
    """Dispatcher for ``mcp`` routes, handling CORS preflight and JSON-RPC payloads."""

    routing_type = 'mcp'

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @classmethod
    def is_compatible_with(cls, request: Request) -> bool:
        """Report whether this dispatcher can serve the given request."""
        return True

    def pre_dispatch(self, rule: Rule, args: dict[str, Any]) -> None:
        """Apply CORS headers and content limits, answering OPTIONS preflight early.

        :raise werkzeug.exceptions.HTTPException: aborts with a 204 response when the
            request is a CORS preflight ``OPTIONS`` call.
        """
        routing = rule.endpoint.routing
        self.request.session.can_save &= routing.get(
            'save_session',
            True,
        )
        self.request.future_response.headers.set(
            'Connection',
            'close',
        )
        if cors := routing.get('cors'):
            set_header = self.request.future_response.headers.set
            methods = routing['methods'] or ['GET', 'POST', 'DELETE']
            set_header('Access-Control-Allow-Origin', cors)
            set_header('Access-Control-Allow-Methods', ', '.join(methods))
            set_header('Access-Control-Expose-Headers', MCP_CORS_RESPONSE_HEADERS)
            set_header('Vary', 'Origin')
            if self.request.httprequest.method == 'OPTIONS':
                set_header('Access-Control-Max-Age', CORS_MAX_AGE)
                set_header('Access-Control-Allow-Headers', MCP_CORS_REQUEST_HEADERS)
                werkzeug.exceptions.abort(Response(status=204))
        if (limit := routing.get('max_content_length')) is not None:
            self.request.httprequest.max_content_length = (
                limit(rule.endpoint.func.__self__) if callable(limit) else limit
            )

    def dispatch(self, endpoint: Callable, args: dict[str, Any]) -> Response:
        """Parse any JSON body into ``jsonrpc_data``/``jsonrpc_batch`` then run the endpoint."""
        self.request.params = {**args, **self.request.get_http_params()}
        if self.request.httprequest.mimetype == 'application/json':
            body = self.request.httprequest.get_data(as_text=True)
            if body:
                try:
                    data = json.loads(body)
                    if isinstance(data, dict):
                        self.request.params['jsonrpc_data'] = data
                    elif isinstance(data, list):
                        self.request.params['jsonrpc_batch'] = data
                except (json.JSONDecodeError, TypeError, ValueError):
                    pass
        result = (
            self.request.registry['ir.http']._dispatch(endpoint)
            if self.request.db
            else endpoint(**self.request.params)
        )
        if isinstance(result, Response):
            return result
        return self.request.make_json_response(result)

    def handle_error(self, exc: Exception) -> Response | HTTPException:
        """Convert an uncaught exception into a JSON-RPC internal error response."""
        if isinstance(exc, HTTPException):
            return exc
        error = {
            'jsonrpc': '2.0',
            'id': None,
            'error': {
                'code': -32603,
                'message': str(exc),
            },
        }
        return self.request.make_json_response(error, status=500)
