from __future__ import annotations

import json
from typing import Any

from odoo.addons.muk_mcp.tools import common, version


class ToolContent(list):
    """List marker type for a sequence of MCP content blocks."""


class ToolResult(dict):
    """Dict marker type for a structured MCP tool result."""


def make_jsonrpc_response(
    result: Any,
    request_id: Any = None,
) -> dict[str, Any]:
    """Build a JSON-RPC success response wrapping ``result``."""
    return {
        'jsonrpc': common.JSONRPC_VERSION,
        'id': request_id,
        'result': result,
    }


def make_jsonrpc_error(
    code: int,
    message: str,
    data: Any = None,
    request_id: Any = None,
) -> dict[str, Any]:
    """Build a JSON-RPC error response with the given code, message, and data."""
    error = {
        'code': code,
        'message': message,
    }
    if data is not None:
        error['data'] = data
    return {
        'jsonrpc': common.JSONRPC_VERSION,
        'id': request_id,
        'error': error,
    }


def parse_jsonrpc_request(
    raw_body: str | bytes | dict[str, Any],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Validate a raw JSON-RPC request body.

    Rejects array ``params``: JSON-RPC 2.0 permits them, but every MCP method
    takes an object, and validating here lets each handler assume a mapping.

    :return: a ``(request, None)`` pair on success, or ``(None, error)`` with a
        ready-to-send JSON-RPC error response on failure.
    """
    try:
        data = json.loads(raw_body) if isinstance(raw_body, (str, bytes)) else raw_body
    except (json.JSONDecodeError, TypeError, ValueError):
        return None, make_jsonrpc_error(
            common.JSONRPC_PARSE_ERROR,
            'Parse error',
        )
    if not isinstance(data, dict):
        return None, make_jsonrpc_error(
            common.JSONRPC_INVALID_REQUEST,
            'Invalid Request: expected JSON object',
        )
    if data.get('jsonrpc') != common.JSONRPC_VERSION:
        return None, make_jsonrpc_error(
            common.JSONRPC_INVALID_REQUEST,
            'Invalid Request: jsonrpc must be "2.0"',
            request_id=data.get('id'),
        )
    method = data.get('method')
    if not method or not isinstance(method, str):
        return None, make_jsonrpc_error(
            common.JSONRPC_INVALID_REQUEST,
            'Invalid Request: method is required',
            request_id=data.get('id'),
        )
    params = data.get('params')
    if params is not None and not isinstance(params, dict):
        return None, make_jsonrpc_error(
            common.JSONRPC_INVALID_REQUEST,
            'Invalid Request: params must be an object',
            request_id=data.get('id'),
        )
    return data, None


def make_server_capabilities(
    capabilities: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the advertised server capabilities, merging in any extra entries."""
    caps = {
        'tools': {'listChanged': True},
        'prompts': {'listChanged': True},
        'resources': {'subscribe': False, 'listChanged': False},
        'completions': {},
    }
    if capabilities:
        caps.update(capabilities)
    return caps


def make_server_info() -> dict[str, Any]:
    """Build the server identity block shared by initialize and discover."""
    return {
        'name': common.MCP_SERVER_NAME,
        'version': common.MCP_SERVER_VERSION,
    }


def make_initialize_result(
    negotiated_version: str,
    capabilities: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the MCP ``initialize`` result for the negotiated revision."""
    return {
        'protocolVersion': negotiated_version,
        'capabilities': make_server_capabilities(capabilities),
        'serverInfo': make_server_info(),
    }


def make_discover_result(
    capabilities: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the MCP ``server/discover`` result advertising every served revision."""
    return {
        'supportedVersions': list(version.MCP_SUPPORTED_VERSIONS),
        'capabilities': make_server_capabilities(capabilities),
        'serverInfo': make_server_info(),
    }


def make_unsupported_version_error(
    requested: Any,
    request_id: Any = None,
) -> dict[str, Any]:
    """Build the JSON-RPC error returned for a protocol revision we do not serve."""
    return make_jsonrpc_error(
        common.MCP_UNSUPPORTED_PROTOCOL_VERSION,
        f'Unsupported protocol version: {requested}',
        data={
            'supported': list(version.MCP_SUPPORTED_VERSIONS),
            'requested': requested,
        },
        request_id=request_id,
    )


def make_tool_result(
    content: Any,
    is_error: bool = False,
    structured_content: Any = None,
) -> dict[str, Any]:
    """Build an MCP tool result, optionally flagged as an error or structured."""
    result = {'content': content}
    if is_error:
        result['isError'] = True
    if structured_content is not None:
        result['structuredContent'] = structured_content
    return result


def make_text_content(text: Any) -> dict[str, Any]:
    """Build a text content block, stringifying ``text``."""
    return {
        'type': 'text',
        'text': str(text),
    }


def make_prompt_message(role: str, text: Any) -> dict[str, Any]:
    """Build a prompt message pairing ``role`` with a text content block."""
    return {
        'role': role,
        'content': make_text_content(text),
    }


def make_image_content(data: str, mime_type: str) -> dict[str, Any]:
    """Build an image content block from base64 ``data`` and its MIME type."""
    return {
        'type': 'image',
        'data': data,
        'mimeType': mime_type,
    }


def make_audio_content(data: str, mime_type: str) -> dict[str, Any]:
    """Build an audio content block from base64 ``data`` and its MIME type."""
    return {
        'type': 'audio',
        'data': data,
        'mimeType': mime_type,
    }


def make_resource_content(
    uri: str,
    mime_type: str | None = None,
    *,
    text: str | None = None,
    blob: str | None = None,
    name: str | None = None,
) -> dict[str, Any]:
    """Build a resource content block for ``uri`` with optional text or blob body."""
    resource = {'uri': uri}
    if mime_type:
        resource['mimeType'] = mime_type
    if name:
        resource['name'] = name
    if text is not None:
        resource['text'] = text
    if blob is not None:
        resource['blob'] = blob
    return {
        'type': 'resource',
        'resource': resource,
    }
