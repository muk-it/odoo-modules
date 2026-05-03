import base64
import json
import time

from functools import partial

from odoo import http
from odoo.http import request, Response
from odoo.tools import SQL, config
from odoo.service.model import retrying
from odoo.exceptions import AccessError, UserError

from odoo.addons.muk_mcp.core.route import mcp_route
from odoo.addons.muk_mcp.tools import common, protocol
from odoo.addons.muk_mcp.tools.content import (
    is_textual_mimetype, normalize_mimetype
)
from odoo.addons.muk_mcp.tools.exception import MCPScopeDenied

class MCPController(http.Controller):

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _check_rate_limit(self, count=1):
        if key := getattr(request, '_mcp_key', None):
            if not key._check_rate_limit(count=count):
                self._log_request(
                    'rate_limited', status='rate_limited',
                )
                return False
        return True

    def _log_request(self, method, **kwargs):
        if config.get('mcp_logging', True):
            key = getattr(request, '_mcp_key', None)
            request.env['muk_mcp.log'].log(
                key_id=key.id if key else None,
                user_id=request.env.uid,
                method=method,
                ip_address=request.httprequest.remote_addr,
                **kwargs,
            )

    def _get_session(self, session_id):
        if session := request.env['muk_mcp.session'].sudo().search([
            ('session_id', '=', session_id),
            ('user_id', '=', request.env.uid),
            ('active', '=', True),
        ], limit=1):
            return session._touch()
        return None

    def _require_session(self):
        session_id = request.httprequest.headers.get('Mcp-Session-Id')
        if not session_id:
            return None, Response(status=400)
        if not (session := self._get_session(session_id)):
            return None, Response(status=404)
        return session, None

    def _claim_notifications(self, session_id, after_id=0):
        table = SQL.identifier('muk_mcp_notification')
        request.env.cr.execute(SQL(
            """
            UPDATE %s SET delivered = true
             WHERE id IN (
                SELECT id FROM %s
                 WHERE session_id = %s AND delivered = false AND id > %s
                 ORDER BY id ASC LIMIT 50
                   FOR UPDATE SKIP LOCKED
             ) RETURNING id, event_id, method, params
            """,
            table, table, session_id, after_id,
        ))
        return request.env.cr.fetchall()

    def _make_sse_response(self, rows):
        chunks = [b'retry: 10000\n\n']
        for _id, event_id, method, params in rows:
            msg = json.dumps({
                'jsonrpc': '2.0',
                'method': method,
                'params': json.loads(params) if params else {},
            }, ensure_ascii=False, default=str)
            chunks.append(
                f'id: {event_id}\nevent: message\ndata: {msg}\n\n'.encode()
            )
        if len(chunks) == 1:
            chunks.append(b':keepalive\n\n')
        return Response(
            b''.join(chunks), status=200,
            headers={
                'Content-Type': 'text/event-stream',
                'Cache-Control': 'no-cache',
                'X-Accel-Buffering': 'no',
            },
        )

    def _dispatch_method(self, data):
        method, params, request_id = (
            data.get('method'),
            data.get('params', {}),
            data.get('id'),
        )
        handlers = {
            'ping': lambda p: {},
            'initialize': self._handle_initialize,
            'notifications/initialized': self._handle_initialized,
            'notifications/roots/list_changed': lambda p: None,
            'notifications/cancelled': lambda p: None,
            'tools/list': self._handle_tools_list,
            'tools/call': self._handle_tools_call,
            'resources/list': lambda p: {'resources': []},
            'resources/read': self._handle_resources_read,
            'resources/templates/list': self._handle_resource_templates_list,
            'prompts/list': lambda p: {'prompts': []},
            'prompts/get': lambda p: {'messages': []},
            'completion/complete': lambda p: {
                'completion': {
                    'values': [], 
                    'total': 0, 
                    'hasMore': False
                },
            },
            'logging/setLevel': lambda p: {},
        }
        if not (handler := handlers.get(method)):
            self._log_request(
                method,
                status='error',
                error_message=f'Method not found: {method}',
            )
            return protocol.make_jsonrpc_error(
                common.JSONRPC_METHOD_NOT_FOUND,
                f'Method not found: {method}',
                request_id=request_id,
            )
        requires_initialized = method not in (
            'ping', 'initialize', 'notifications/initialized',
        )
        if requires_initialized:
            if not (sid := request.httprequest.headers.get('Mcp-Session-Id')):
                return protocol.make_jsonrpc_error(
                    common.JSONRPC_INVALID_REQUEST,
                    'Session required',
                    request_id=request_id,
                )
            if (
                not (session := self._get_session(sid)) or 
                not session.initialized
            ):
                return protocol.make_jsonrpc_error(
                    common.JSONRPC_INVALID_REQUEST,
                    'Session not initialized',
                    request_id=request_id,
                )
        is_tool_call = method == 'tools/call'
        start = time.time()
        try:
            result = handler(params)
        except Exception as exc:
            if not is_tool_call:
                self._log_request(
                    method,
                    status='error',
                    error_message=str(exc),
                    duration_ms=int((time.time() - start) * 1000),
                )
            return protocol.make_jsonrpc_error(
                common.JSONRPC_INTERNAL_ERROR,
                'Internal server error',
                request_id=request_id,
            )
        if method.startswith('notifications/'):
            return None
        return protocol.make_jsonrpc_response(result, request_id=request_id)

    def _handle_batch(self, items):
        if len(items) > common.MAX_BATCH_SIZE:
            return request.make_json_response(
                protocol.make_jsonrpc_error(
                    common.JSONRPC_INVALID_REQUEST,
                    f'Batch too large (max {common.MAX_BATCH_SIZE})',
                ),
                status=400,
            )
        if not self._check_rate_limit(count=len(items)):
            return request.make_json_response(
                protocol.make_jsonrpc_error(
                    common.JSONRPC_INTERNAL_ERROR,
                    'Rate limit exceeded',
                ),
                status=429,
            )
        results = []
        for item in items:
            data, error = protocol.parse_jsonrpc_request(item)
            if error is not None:
                results.append(error)
            elif (result := self._dispatch_method(data)) is not None:
                results.append(result)
        return request.make_json_response(results)

    def _handle_initialize(self, params):
        session = request.env['muk_mcp.session'].sudo().create({
            'user_id': request.env.uid,
            'initialized': False,
        })
        request._mcp_new_session_id = session.session_id
        return protocol.make_initialize_result()

    def _handle_initialized(self, params):
        session_id = request.httprequest.headers.get('Mcp-Session-Id')
        if session_id and (session := self._get_session(session_id)):
            session.write({'initialized': True})
        return None

    def _handle_tools_list(self, params):
        return {
            'tools': request.env['muk_mcp.tool'].sudo().get_tools(
                registry='mcp'
            )
        }

    def _handle_tools_call(self, params):
        if not (tool_name := params.get('name')):
            return protocol.make_tool_result(
                [protocol.make_text_content('Tool name is required')],
                is_error=True,
            )
        key = getattr(request, '_mcp_key', None)
        enforce_scope = key.scope if key else None
        try:
            result, _record_info = retrying(
                partial(
                    request.env['muk_mcp.tool']._call,
                    tool_name,
                    params.get('arguments', {}),
                    request.env,
                    enforce_scope=enforce_scope,
                ),
                request.env,
            )
        except MCPScopeDenied as exc:
            return protocol.make_tool_result(
                [protocol.make_text_content(str(exc))],
                is_error=True,
            )
        except (AccessError, UserError) as exc:
            return protocol.make_tool_result(
                [protocol.make_text_content(str(exc))],
                is_error=True,
            )
        except Exception:
            return protocol.make_tool_result(
                [protocol.make_text_content('Internal server error')],
                is_error=True,
            )
        if isinstance(result, protocol.ToolContent):
            return protocol.make_tool_result(result)
        return protocol.make_tool_result(
            [protocol.make_text_content(result)]
        )

    def _handle_resources_read(self, params):
        if not (uri := (params or {}).get('uri')):
            return {'contents': []}
        try:
            mimetype, raw, name = (
                request.env['muk_mcp.mixin']._resolve_resource_uri(
                    uri
                )
            )
        except (UserError, AccessError):
            return {'contents': []}
        normalized = normalize_mimetype(
            mimetype
        )
        entry = {'uri': uri}
        if normalized:
            entry['mimeType'] = normalized
        if name:
            entry['name'] = name
        if is_textual_mimetype(normalized):
            try:
                entry['text'] = raw.decode('utf-8')
            except UnicodeDecodeError:
                entry['blob'] = base64.b64encode(raw).decode(
                    'ascii'
                )
        else:
            entry['blob'] = base64.b64encode(raw).decode(
                'ascii'
            )
        return {'contents': [entry]}

    def _handle_resource_templates_list(self, params):
        return {
            'resourceTemplates': [
                {
                    'uriTemplate': 'odoo://attachment/{attachment_id}',
                    'name': 'ir.attachment',
                    'description': 'A file stored as an ir.attachment record.',
                },
                {
                    'uriTemplate': 'odoo://record/{model}/{id}/{field}',
                    'name': 'record-binary-field',
                    'description': (
                        'A Binary field on an Odoo record (image, signature, '
                        'document, etc.). Mimetype is auto-detected.'
                    ),
                },
            ],
        }

    # ----------------------------------------------------------
    # Routes
    # ----------------------------------------------------------

    @mcp_route('/mcp', methods=['POST'])
    def mcp_post(self, **kw):
        if not self._check_rate_limit():
            return request.make_json_response(
                protocol.make_jsonrpc_error(
                    common.JSONRPC_INTERNAL_ERROR,
                    'Rate limit exceeded',
                ),
                status=429,
            )
        if (batch := request.params.get('jsonrpc_batch')) is not None:
            return self._handle_batch(batch)
        if (data := request.params.get('jsonrpc_data')) is None:
            return request.make_json_response(
                protocol.make_jsonrpc_error(
                    common.JSONRPC_PARSE_ERROR,
                    'Parse error',
                ),
                status=400,
            )
        data, error = protocol.parse_jsonrpc_request(data)
        if error is not None:
            return request.make_json_response(error, status=400)
        if (response_data := self._dispatch_method(data)) is None:
            return Response(status=202)
        headers = {}
        if new_sid := getattr(request, '_mcp_new_session_id', None):
            headers['Mcp-Session-Id'] = new_sid
        return request.make_json_response(response_data, headers=headers)

    @mcp_route('/mcp', methods=['GET'])
    def mcp_get(self, **kw):
        if (
            'text/event-stream' not in
            request.httprequest.headers.get('Accept', '')
        ):
            return Response(status=405)
        session, error = self._require_session()
        if error:
            return error
        after_id = 0
        if last_event_id := request.httprequest.headers.get('Last-Event-ID'):
            if resume := request.env['muk_mcp.notification'].search(
                [('event_id', '=', last_event_id)], limit=1,
            ):
                after_id = resume.id
        return self._make_sse_response(
            self._claim_notifications(session.id, after_id)
        )

    @mcp_route('/mcp', methods=['DELETE'])
    def mcp_delete(self, **kw):
        if session := self._get_session(
            request.httprequest.headers.get('Mcp-Session-Id')
        ):
            session.write({'active': False})
        return Response(status=200)
