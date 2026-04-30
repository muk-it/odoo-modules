import json

from odoo import http


_root_get_request = http.Root.get_request


class MCPRequest(http.HttpRequest):
    def __init__(self, *args):
        super().__init__(*args)
        if self.httprequest.method != 'POST':
            return
        body = self.httprequest.get_data(as_text=True)
        if not body:
            return
        try:
            payload = json.loads(body)
        except (json.JSONDecodeError, TypeError, ValueError):
            return
        if isinstance(payload, list):
            self.params['jsonrpc_batch'] = payload
        elif isinstance(payload, dict):
            self.params['jsonrpc_data'] = payload


def _mcp_get_request(self, httprequest):
    if httprequest.path.startswith('/mcp'):
        return MCPRequest(httprequest)
    return _root_get_request(self, httprequest)


http.Root.get_request = _mcp_get_request
