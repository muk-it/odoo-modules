from __future__ import annotations

import json
import time
import traceback
from functools import partial
from typing import Any

from odoo import http, models
from odoo.exceptions import AccessError, UserError
from odoo.http import Response, request
from odoo.service.model import retrying
from odoo.tools import SQL, config

from odoo.addons.muk_mcp.core.route import mcp_route
from odoo.addons.muk_mcp.tools import common, protocol
from odoo.addons.muk_mcp.tools.exception import MCPScopeDenied


class MCPController(http.Controller):
    """HTTP endpoints implementing the MCP JSON-RPC protocol over POST, GET and DELETE."""

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _get_request_rate_limiter(self) -> models.BaseModel | None:
        """Return the rate-limiter record bound to the request, if any."""
        return getattr(request, '_mcp_key', None)

    def _check_rate_limit(self, count: int = 1) -> bool:
        """Reject and log the request when its rate-limiter is over its limit."""
        limiter = self._get_request_rate_limiter()
        if limiter and not limiter._check_rate_limit(count=count):
            self._log_request(
                'rate_limited',
                status='rate_limited',
            )
            return False
        return True

    def _log_request(self, method: str, **kwargs: Any) -> None:
        """Write an MCP audit-log row for the request when logging is enabled."""
        if config.get('mcp_logging', True):
            key = getattr(request, '_mcp_key', None)
            request.env['muk_mcp.log'].log(
                key_name=key.name if key else None,
                key_prefix=key.key_prefix if key else None,
                user_id=request.env.uid,
                method=method,
                ip_address=request.httprequest.remote_addr,
                **kwargs,
            )

    def _format_internal_error(self, exc: Exception) -> str:
        """Build an error message, appending the traceback when ``mcp_debug`` is set."""
        message = f'Internal server error: {exc}'
        if config.get('mcp_debug', False):
            trace = ''.join(
                traceback.format_exception(
                    exc.__class__,
                    exc,
                    exc.__traceback__,
                ),
            )
            message += f'\n\n{trace}'
        return message

    def _get_tool_enforce_scope(self) -> str | None:
        """Return the scope to enforce on tool calls, derived from the API key."""
        key = getattr(request, '_mcp_key', None)
        return key.scope if key else None

    def _get_session(self, session_id: str | None) -> models.BaseModel | None:
        """Return the active session for the current user, refreshing its last-seen time."""
        if (
            session := request.env['muk_mcp.session']
            .sudo()
            .search(
                [
                    ('session_id', '=', session_id),
                    ('user_id', '=', request.env.uid),
                    ('active', '=', True),
                ],
                limit=1,
            )
        ):
            return session._touch()
        return None

    def _require_session(self) -> tuple[models.BaseModel | None, Response | None]:
        """Resolve the session from the request header.

        :return: ``(session, None)`` on success, or ``(None, error_response)`` with a 400
            when the header is missing or a 404 when no matching session exists.
        """
        session_id = request.httprequest.headers.get('Mcp-Session-Id')
        if not session_id:
            return None, Response(status=400)
        if not (session := self._get_session(session_id)):
            return None, Response(status=404)
        return session, None

    def _claim_notifications(self, session_id: int, after_id: int = 0) -> list[tuple]:
        """Atomically claim up to 50 undelivered notifications for a session.

        Uses ``FOR UPDATE SKIP LOCKED`` so concurrent SSE readers never claim the same
        rows, marking the selected rows delivered and returning them ordered by id.

        :param after_id: only claim notifications with a higher id (for resume support).
        """
        table = SQL.identifier('muk_mcp_notification')
        request.env.cr.execute(
            SQL(
                """
            UPDATE %s SET delivered = true
             WHERE id IN (
                SELECT id FROM %s
                 WHERE session_id = %s AND delivered = false AND id > %s
                 ORDER BY id ASC LIMIT 50
                   FOR UPDATE SKIP LOCKED
             ) RETURNING id, event_id, method, params
            """,
                table,
                table,
                session_id,
                after_id,
            ),
        )
        return request.env.cr.fetchall()

    def _make_sse_response(self, rows: list[tuple]) -> Response:
        """Render claimed notification rows as a ``text/event-stream`` SSE response.

        Emits a keepalive comment when there are no rows so the stream is never empty.
        """
        chunks = [b'retry: 10000\n\n']
        for _id, event_id, method, params in rows:
            msg = json.dumps(
                {
                    'jsonrpc': '2.0',
                    'method': method,
                    'params': json.loads(params) if params else {},
                },
                ensure_ascii=False,
                default=str,
            )
            chunks.append(
                f'id: {event_id}\nevent: message\ndata: {msg}\n\n'.encode(),
            )
        if len(chunks) == 1:
            chunks.append(b':keepalive\n\n')
        return Response(
            b''.join(chunks),
            status=200,
            headers={
                'Content-Type': 'text/event-stream',
                'Cache-Control': 'no-cache',
                'X-Accel-Buffering': 'no',
            },
        )

    def _dispatch_method(self, data: dict[str, Any]) -> dict[str, Any] | None:
        """Route one parsed JSON-RPC request to its handler and wrap the outcome.

        Enforces that an initialized session exists for every method except ``ping``,
        ``initialize`` and ``notifications/initialized``, and maps handler exceptions to
        JSON-RPC errors.

        :return: a JSON-RPC response or error dict, or ``None`` for notifications (which
            produce no reply).
        """
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
            'resources/list': self._handle_resources_list,
            'resources/read': self._handle_resources_read,
            'resources/templates/list': self._handle_resource_templates_list,
            'prompts/list': self._handle_prompts_list,
            'prompts/get': self._handle_prompts_get,
            'completion/complete': self._handle_completion_complete,
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
            'ping',
            'initialize',
            'notifications/initialized',
        )
        if requires_initialized:
            if not (sid := request.httprequest.headers.get('Mcp-Session-Id')):
                return protocol.make_jsonrpc_error(
                    common.JSONRPC_INVALID_REQUEST,
                    'Session required',
                    request_id=request_id,
                )
            if not (session := self._get_session(sid)) or not session.initialized:
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
                self._format_internal_error(exc),
                request_id=request_id,
            )
        if method.startswith('notifications/'):
            return None
        return protocol.make_jsonrpc_response(result, request_id=request_id)

    def _handle_batch(self, items: list[dict[str, Any]]) -> Response:
        """Dispatch a JSON-RPC batch, enforcing size and rate limits.

        Collects only non-null results (notifications are dropped) into a single response.
        """
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

    def _handle_initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle ``initialize``: create a session and return the server capabilities.

        Stashes the new session id on the request so the route can return it as the
        ``Mcp-Session-Id`` response header.
        """
        session = (
            request.env['muk_mcp.session']
            .sudo()
            .create(
                {
                    'user_id': request.env.uid,
                    'initialized': False,
                },
            )
        )
        request._mcp_new_session_id = session.session_id
        return protocol.make_initialize_result(
            capabilities=self._get_capabilities(params),
        )

    def _get_capabilities(self, params: dict[str, Any]) -> dict[str, Any]:
        """Return the server capabilities advertised in the initialize result."""
        return {}

    def _handle_initialized(self, params: dict[str, Any]) -> None:
        """Handle the ``notifications/initialized`` notification by marking the session ready."""
        session_id = request.httprequest.headers.get('Mcp-Session-Id')
        if session_id and (session := self._get_session(session_id)):
            session.write({'initialized': True})
        return

    def _handle_tools_list(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle ``tools/list``: return the tools registered for the ``mcp`` registry."""
        return {
            'tools': request.env['muk_mcp.tool']
            .sudo()
            .get_tools(
                registry='mcp',
            ),
        }

    def _handle_tools_call(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle ``tools/call``: run the named tool, enforcing the API key scope.

        Executes the tool under ``retrying`` for serialization-failure safety and converts
        scope, access, user and unexpected errors into MCP tool error results rather than
        protocol-level errors.
        """
        if not (tool_name := params.get('name')):
            return protocol.make_tool_result(
                [protocol.make_text_content('Tool name is required')],
                is_error=True,
            )
        enforce_scope = self._get_tool_enforce_scope()
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
        except Exception as exc:
            return protocol.make_tool_result(
                [
                    protocol.make_text_content(
                        self._format_internal_error(exc),
                    ),
                ],
                is_error=True,
            )
        if isinstance(result, protocol.ToolResult):
            return dict(result)
        if isinstance(result, protocol.ToolContent):
            return protocol.make_tool_result(result)
        return protocol.make_tool_result(
            [protocol.make_text_content(result)],
        )

    def _handle_resources_list(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle ``resources/list``: no concrete resources are enumerated (templates only)."""
        return {'resources': []}

    def _handle_resources_read(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle ``resources/read``: resolve the URI to content, empty on access denial."""
        if not (uri := (params or {}).get('uri')):
            return {'contents': []}
        try:
            entry = request.env['muk_mcp.mixin']._dispatch_resources_read(
                uri,
            )
        except AccessError:
            return {'contents': []}
        if not entry:
            return {'contents': []}
        return {'contents': [entry]}

    def _handle_resource_templates_list(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle ``resources/templates/list``: advertise attachment and binary-field URIs."""
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

    def _handle_prompts_list(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle ``prompts/list``: return all registered prompt definitions."""
        return {
            'prompts': request.env['muk_mcp.prompt'].sudo().get_prompts(),
        }

    def _handle_prompts_get(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle ``prompts/get``: render the named prompt with the supplied arguments."""
        return (
            request.env['muk_mcp.prompt']
            .sudo()
            .get_prompt(
                params.get('name'),
                params.get('arguments') or {},
            )
        )

    def _handle_completion_complete(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle ``completion/complete``: suggest values for a prompt argument."""
        return (
            request.env['muk_mcp.prompt']
            .sudo()
            .complete_argument(
                params.get('ref') or {},
                params.get('argument') or {},
            )
        )

    # ----------------------------------------------------------
    # Routes
    # ----------------------------------------------------------

    @mcp_route('/mcp', methods=['POST'])
    def mcp_post(self, **kw: Any) -> Response:
        """Serve JSON-RPC requests: dispatch single or batch calls and return the reply.

        :return: a JSON response, a 202 for notifications, or a 429 when rate limited;
            a freshly created session id is echoed in the ``Mcp-Session-Id`` header.
        """
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
    def mcp_get(self, **kw: Any) -> Response:
        """Open the SSE notification stream for a session, supporting ``Last-Event-ID`` resume.

        :return: a ``text/event-stream`` response, or 405 when SSE is not requested.
        """
        if 'text/event-stream' not in request.httprequest.headers.get('Accept', ''):
            return Response(status=405)
        session, error = self._require_session()
        if error:
            return error
        after_id = 0
        if last_event_id := request.httprequest.headers.get('Last-Event-ID'):
            if resume := request.env['muk_mcp.notification'].search(
                [('event_id', '=', last_event_id)],
                limit=1,
            ):
                after_id = resume.id
        return self._make_sse_response(
            self._claim_notifications(session.id, after_id),
        )

    @mcp_route('/mcp', methods=['DELETE'])
    def mcp_delete(self, **kw: Any) -> Response:
        """Terminate the session named in the request header by deactivating it."""
        if session := self._get_session(
            request.httprequest.headers.get('Mcp-Session-Id'),
        ):
            session.write({'active': False})
        return Response(status=200)
