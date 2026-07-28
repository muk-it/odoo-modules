import json

MCP_SERVER_NAME = 'odoo-mcp-server'
MCP_SERVER_VERSION = '1.0.0'

JSONRPC_VERSION = '2.0'

JSONRPC_PARSE_ERROR = -32700
JSONRPC_INVALID_REQUEST = -32600
JSONRPC_METHOD_NOT_FOUND = -32601
JSONRPC_INVALID_PARAMS = -32602
JSONRPC_INTERNAL_ERROR = -32603

MCP_UNSUPPORTED_PROTOCOL_VERSION = -32022


def coerce_json_value(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return value
    return value
