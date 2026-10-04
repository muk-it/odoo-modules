from __future__ import annotations

import base64

MCP_VERSION_2025_06_18 = '2025-06-18'
MCP_VERSION_2025_11_25 = '2025-11-25'
MCP_VERSION_2026_07_28 = '2026-07-28'

MCP_STATELESS_VERSION = MCP_VERSION_2026_07_28
MCP_HANDSHAKE_VERSIONS = (MCP_VERSION_2025_11_25, MCP_VERSION_2025_06_18)
MCP_SUPPORTED_VERSIONS = (MCP_STATELESS_VERSION, *MCP_HANDSHAKE_VERSIONS)

MCP_PROTOCOL_VERSION_HEADER = 'MCP-Protocol-Version'
MCP_METHOD_HEADER = 'Mcp-Method'
MCP_NAME_HEADER = 'Mcp-Name'

MCP_NAME_METHODS = frozenset({'prompts/get', 'resources/read', 'tools/call'})

MCP_HEADER_BASE64_PREFIX = '=?base64?'
MCP_HEADER_BASE64_SUFFIX = '?='

META_PROTOCOL_VERSION = 'io.modelcontextprotocol/protocolVersion'
META_CLIENT_INFO = 'io.modelcontextprotocol/clientInfo'
META_CLIENT_CAPABILITIES = 'io.modelcontextprotocol/clientCapabilities'
META_SERVER_INFO = 'io.modelcontextprotocol/serverInfo'

MCP_CACHE_HINTS = {
    'server/discover': {'ttlMs': 300000, 'cacheScope': 'public'},
    'resources/templates/list': {'ttlMs': 300000, 'cacheScope': 'public'},
    'tools/list': {'ttlMs': 60000, 'cacheScope': 'private'},
    'prompts/list': {'ttlMs': 60000, 'cacheScope': 'private'},
    'resources/list': {'ttlMs': 60000, 'cacheScope': 'private'},
    'resources/read': {'ttlMs': 0, 'cacheScope': 'private'},
}


def negotiate_handshake(requested: str | None) -> str:
    """Return the revision to answer an ``initialize`` handshake with.

    A client naming a revision without a handshake, or one this server does not
    serve, is offered the newest handshake revision, as the lifecycle asks.
    """
    if requested in MCP_HANDSHAKE_VERSIONS:
        return requested
    return MCP_HANDSHAKE_VERSIONS[0]


def decode_header_value(value: str) -> str | None:
    """Decode the Base64 sentinel a mirrored request header value may carry.

    :return: the decoded value, or ``None`` when the sentinel payload is malformed.
    """
    if not (
        value.startswith(MCP_HEADER_BASE64_PREFIX)
        and value.endswith(MCP_HEADER_BASE64_SUFFIX)
    ):
        return value
    payload = value[len(MCP_HEADER_BASE64_PREFIX) : -len(MCP_HEADER_BASE64_SUFFIX)]
    try:
        return base64.b64decode(payload, validate=True).decode('utf-8')
    except (ValueError, UnicodeDecodeError):
        return None
