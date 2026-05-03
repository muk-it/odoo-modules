import json

from . import common


def make_jsonrpc_response(result, request_id=None):
    return {
        'jsonrpc': common.JSONRPC_VERSION,
        'id': request_id,
        'result': result,
    }


def make_jsonrpc_error(
    code,
    message,
    data=None,
    request_id=None,
):
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


def parse_jsonrpc_request(raw_body):
    try:
        data = (
            json.loads(raw_body)
            if isinstance(raw_body, (str, bytes))
            else raw_body
        )
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
    return data, None


def make_initialize_result(capabilities=None):
    caps = {
        'tools': {'listChanged': True},
        'resources': {'subscribe': False, 'listChanged': False},
    }
    if capabilities:
        caps.update(capabilities)
    return {
        'protocolVersion': common.MCP_PROTOCOL_VERSION,
        'capabilities': caps,
        'serverInfo': {
            'name': common.MCP_SERVER_NAME,
            'version': common.MCP_SERVER_VERSION,
        },
    }


def make_tool_result(content, is_error=False):
    result = {'content': content}
    if is_error:
        result['isError'] = True
    return result


def make_text_content(text):
    return {
        'type': 'text',
        'text': str(text),
    }


def make_image_content(data, mime_type):
    return {
        'type': 'image',
        'data': data,
        'mimeType': mime_type,
    }


def make_audio_content(data, mime_type):
    return {
        'type': 'audio',
        'data': data,
        'mimeType': mime_type,
    }


def make_resource_content(
    uri,
    mime_type=None,
    *,
    text=None,
    blob=None,
    name=None
):
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


class ToolContent(list):
    pass
