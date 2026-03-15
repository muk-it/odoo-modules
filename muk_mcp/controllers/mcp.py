import json
import time

import odoo

from odoo import http
from odoo.http import request, Response

from odoo.addons.muk_mcp.tools import common, protocol

SSE_POLL_INTERVAL = 2
SSE_KEEPALIVE_INTERVAL = 15
SSE_MAX_DURATION = 300


class MCPController(http.Controller):

    #----------------------------------------------------------
    # Helper
    #----------------------------------------------------------

    def _check_enabled(self):
        enabled = request.env['ir.config_parameter'].sudo().get_param(
            'muk_mcp.enabled', 'True'
        )
        if isinstance(enabled, str):
            return enabled.strip().lower() not in ('0', 'false', 'no', '')
        return bool(enabled)

    def _get_mcp_key(self):
        return getattr(request, '_mcp_key', None)

    def _check_rate_limit(self):
        mcp_key = self._get_mcp_key()
        if not mcp_key:
            return True
        if not mcp_key._check_rate_limit():
            request.env['muk_mcp.log'].log(
                key_id=mcp_key.id,
                user_id=request.env.uid,
                method='rate_limited',
                status='rate_limited',
            )
            return False
        return True

    def _check_tool_model_access(self, tool_name, arguments):
        mcp_key = self._get_mcp_key()
        if not mcp_key or not mcp_key.scope_ids:
            return True
        model_name = arguments.get('model')
        if not model_name:
            return True
        op_map = {
            'delete_record': 'unlink',
            'create_record': 'create',
        }
        write_tools = {
            'update_record', 'execute_method', 'post_message',
        }
        if tool_name in op_map:
            op = op_map[tool_name]
        elif tool_name in write_tools:
            op = 'write'
        else:
            op = 'read'
        return mcp_key._check_model_access(model_name, op)

    def _log_request(self, method, tool_name=None, model_name=None,
                     status='ok', error_message=None, duration_ms=0):
        mcp_key = self._get_mcp_key()
        request.env['muk_mcp.log'].log(
            key_id=mcp_key.id if mcp_key else None,
            user_id=request.env.uid,
            method=method,
            tool_name=tool_name,
            model_name=model_name,
            status=status,
            error_message=error_message,
            duration_ms=duration_ms,
        )

    def _get_session(self, session_id):
        if not session_id:
            return None
        session = request.env['muk_mcp.session'].sudo().search([
            ('session_id', '=', session_id),
            ('user_id', '=', request.env.uid),
            ('active', '=', True),
        ], limit=1)
        if session:
            session.action_touch()
        return session or None

    def _create_session(self):
        return request.env['muk_mcp.session'].sudo().create({
            'user_id': request.env.uid,
            'initialized': True,
        })

    def _make_json_response(self, data, status=200, headers=None):
        response_headers = {
            'Content-Type': 'application/json; charset=utf-8',
        }
        if headers:
            response_headers.update(headers)
        return Response(
            json.dumps(data, ensure_ascii=False, default=str),
            status=status,
            headers=response_headers,
        )

    def _dispatch_method(self, data):
        method = data.get('method')
        params = data.get('params', {})
        request_id = data.get('id')
        start = time.time()
        handlers = {
            'initialize': self._handle_initialize,
            'notifications/initialized': self._handle_initialized,
            'ping': self._handle_ping,
            'tools/list': self._handle_tools_list,
            'tools/call': self._handle_tools_call,
        }
        handler = handlers.get(method)
        if handler is None:
            self._log_request(method, status='error',
                              error_message=f'Method not found: {method}')
            return protocol.make_jsonrpc_error(
                common.JSONRPC_METHOD_NOT_FOUND,
                f'Method not found: {method}',
                request_id=request_id,
            )
        try:
            result = handler(params)
        except Exception as exc:
            duration = int((time.time() - start) * 1000)
            self._log_request(method, status='error',
                              error_message=str(exc), duration_ms=duration)
            return protocol.make_jsonrpc_error(
                common.JSONRPC_INTERNAL_ERROR,
                str(exc),
                request_id=request_id,
            )
        duration = int((time.time() - start) * 1000)
        if method == 'tools/call':
            self._log_request(
                method,
                tool_name=params.get('name'),
                model_name=params.get('arguments', {}).get('model'),
                duration_ms=duration,
            )
        if method.startswith('notifications/'):
            return None
        return protocol.make_jsonrpc_response(result, request_id=request_id)

    def _handle_batch(self, items):
        results = []
        for item in items:
            data, error = protocol.parse_jsonrpc_request(item)
            if error is not None:
                results.append(error)
                continue
            result = self._dispatch_method(data)
            if result is not None:
                results.append(result)
        return self._make_json_response(results)

    def _handle_initialize(self, params):
        session = self._create_session()
        request._mcp_new_session_id = session.session_id
        return protocol.make_initialize_result()

    def _handle_initialized(self, params):
        return None

    def _handle_ping(self, params):
        return {}

    def _handle_tools_list(self, params):
        tools = request.env['muk_mcp.tool'].sudo().get_tools()
        return {'tools': tools}

    def _handle_tools_call(self, params):
        tool_name = params.get('name')
        arguments = params.get('arguments', {})
        if not tool_name:
            return protocol.make_tool_result(
                [protocol.make_text_content('Tool name is required')],
                is_error=True,
            )
        if not self._check_tool_model_access(tool_name, arguments):
            model_name = arguments.get('model', '')
            self._log_request(
                'tools/call', tool_name=tool_name,
                model_name=model_name, status='denied',
                error_message='Model access denied by key scope',
            )
            return protocol.make_tool_result(
                [protocol.make_text_content(
                    f'Access denied: key does not have permission '
                    f'for {model_name!r} with this operation'
                )],
                is_error=True,
            )
        tool = request.env['muk_mcp.tool'].sudo().search([
            ('name', '=', tool_name),
            ('active', '=', True),
        ], limit=1)
        if not tool:
            return protocol.make_tool_result(
                [protocol.make_text_content(f'Tool not found: {tool_name}')],
                is_error=True,
            )
        try:
            result = tool.action_execute(arguments, request.env)
            return protocol.make_tool_result(
                [protocol.make_text_content(result)]
            )
        except Exception as exc:
            return protocol.make_tool_result(
                [protocol.make_text_content(f'Error: {exc}')],
                is_error=True,
            )

    #----------------------------------------------------------
    # Routes
    #----------------------------------------------------------

    @http.route(
        '/mcp',
        type='mcp',
        auth='mcp',
        methods=['POST'],
        csrf=False,
        save_session=False,
    )
    def mcp_post(self, **kw):
        if not self._check_enabled():
            return self._make_json_response(
                protocol.make_jsonrpc_error(
                    common.JSONRPC_INTERNAL_ERROR,
                    'MCP server is disabled',
                ),
                status=503,
            )
        if not self._check_rate_limit():
            return self._make_json_response(
                protocol.make_jsonrpc_error(
                    common.JSONRPC_INTERNAL_ERROR,
                    'Rate limit exceeded',
                ),
                status=429,
            )
        batch = request.params.get('jsonrpc_batch')
        if batch is not None:
            return self._handle_batch(batch)
        data = request.params.get('jsonrpc_data')
        if data is None:
            return self._make_json_response(
                protocol.make_jsonrpc_error(
                    common.JSONRPC_PARSE_ERROR, 'Parse error',
                ),
                status=400,
            )
        data, error = protocol.parse_jsonrpc_request(data)
        if error is not None:
            return self._make_json_response(error, status=400)
        session_id = request.httprequest.headers.get('Mcp-Session-Id')
        method = data.get('method')
        if method != 'initialize' and session_id:
            session = self._get_session(session_id)
            if not session:
                return self._make_json_response(
                    protocol.make_jsonrpc_error(
                        common.JSONRPC_INVALID_REQUEST,
                        'Invalid or expired session',
                        request_id=data.get('id'),
                    ),
                    status=404,
                )
        response_data = self._dispatch_method(data)
        if response_data is None:
            return Response(status=202)
        headers = {}
        new_session_id = getattr(request, '_mcp_new_session_id', None)
        if new_session_id:
            headers['Mcp-Session-Id'] = new_session_id
        return self._make_json_response(response_data, headers=headers)

    @http.route(
        '/mcp',
        type='mcp',
        auth='mcp',
        methods=['GET'],
        csrf=False,
        save_session=False,
    )
    def mcp_get(self, **kw):
        if not self._check_enabled():
            return Response(status=503)
        accept = request.httprequest.headers.get('Accept', '')
        if 'text/event-stream' not in accept:
            return Response(status=405)
        session_id = request.httprequest.headers.get('Mcp-Session-Id')
        if not session_id:
            return Response(status=400)
        session = self._get_session(session_id)
        if not session:
            return Response(status=404)
        last_event_id = request.httprequest.headers.get('Last-Event-ID')
        db_name = request.env.cr.dbname
        uid = request.env.uid

        def event_stream():
            start_time = time.time()
            last_keepalive = start_time
            nonlocal last_event_id
            while time.time() - start_time < SSE_MAX_DURATION:
                notifications = []
                try:
                    registry = odoo.registry(db_name)
                    with registry.cursor() as cr:
                        env = odoo.api.Environment(cr, uid, {})
                        domain = [
                            ('session_id', '=', session.id),
                            ('delivered', '=', False),
                        ]
                        if last_event_id:
                            resume = env['muk_mcp.notification'].search([
                                ('event_id', '=', last_event_id),
                            ], limit=1)
                            if resume:
                                domain.append(('id', '>', resume.id))
                            last_event_id = None
                        pending = env['muk_mcp.notification'].search(
                            domain, order='id asc', limit=50,
                        )
                        for notif in pending:
                            msg = {
                                'jsonrpc': '2.0',
                                'method': notif.method,
                                'params': (
                                    json.loads(notif.params)
                                    if notif.params else {}
                                ),
                            }
                            notifications.append((notif.event_id, msg))
                        if pending:
                            pending.write({'delivered': True})
                except Exception:
                    pass
                for event_id, msg in notifications:
                    data = json.dumps(msg, ensure_ascii=False, default=str)
                    yield f'id: {event_id}\nevent: message\ndata: {data}\n\n'.encode()
                now = time.time()
                if now - last_keepalive >= SSE_KEEPALIVE_INTERVAL:
                    yield b':keepalive\n\n'
                    last_keepalive = now
                if not notifications:
                    time.sleep(SSE_POLL_INTERVAL)

        return Response(
            event_stream(),
            status=200,
            headers={
                'Content-Type': 'text/event-stream',
                'Cache-Control': 'no-cache',
                'Connection': 'keep-alive',
                'X-Accel-Buffering': 'no',
            },
            direct_passthrough=True,
        )

    @http.route(
        '/mcp',
        type='mcp',
        auth='mcp',
        methods=['DELETE'],
        csrf=False,
        save_session=False,
    )
    def mcp_delete(self, **kw):
        session_id = request.httprequest.headers.get('Mcp-Session-Id')
        if session_id:
            session = self._get_session(session_id)
            if session:
                session.write({'active': False})
        return Response(status=200)
