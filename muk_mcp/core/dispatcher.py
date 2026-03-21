import json

from werkzeug.exceptions import HTTPException

from odoo import http
from odoo.http import Response


class MCPDispatcher(http.Dispatcher):

    routing_type = 'mcp'

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @classmethod
    def is_compatible_with(cls, request):
        return True

    def dispatch(self, endpoint, args):
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

    def handle_error(self, exc):
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
