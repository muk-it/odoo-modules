MCP_PROTOCOL_VERSION = '2025-03-26'
MCP_SERVER_NAME = 'odoo-mcp-server'
MCP_SERVER_VERSION = '1.0.0'

JSONRPC_VERSION = '2.0'

JSONRPC_PARSE_ERROR = -32700
JSONRPC_INVALID_REQUEST = -32600
JSONRPC_METHOD_NOT_FOUND = -32601
JSONRPC_INTERNAL_ERROR = -32603

MAX_BATCH_SIZE = 20

MCP_CORS_REQUEST_HEADERS = (
    'authorization, content-type, accept, origin, '
    'mcp-session-id, mcp-protocol-version, last-event-id'
)

MCP_CORS_RESPONSE_HEADERS = 'mcp-session-id'
