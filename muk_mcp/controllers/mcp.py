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
from odoo.tools.misc import str2bool

from odoo.addons.muk_mcp.core.route import mcp_route
from odoo.addons.muk_mcp.tools import common, protocol, version
from odoo.addons.muk_mcp.tools.exception import MCPScopeDenied
from odoo.addons.muk_mcp.tools.version import ProtocolProfile


class MCPController(http.Controller):
    """HTTP endpoints implementing the MCP JSON-RPC protocol over POST, GET and DELETE."""

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _get_request_rate_limiter(self) -> models.BaseModel | None:
        """Return the rate-limiter record bound to the request, if any."""
        return getattr(request, '_mcp_key', None)

    def _check_rate_limit(self) -> bool:
        """Reject and log the request when its rate-limiter is over its limit."""
        limiter = self._get_request_rate_limiter()
        if limiter and not limiter._check_rate_limit():
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

    def _get_allowed_origins(self) -> set[str]:
        """Return the origins accepted on MCP requests.

        Deliberately built from server-side configuration only. Deriving an entry
        from the request's own ``Host`` would defeat the check it feeds: under DNS
        rebinding the browser sends the rebound name as both ``Host`` and
        ``Origin``, so such an entry would match exactly the attack it is meant
        to stop.
        """
        param = request.env['ir.config_parameter'].sudo()
        configured = param.get_param('muk_mcp.allowed_origins', '') or ''
        origins = {entry.strip().rstrip('/') for entry in configured.split(',')}
        if base_url := param.get_param('web.base.url', ''):
            origins.add(base_url.rstrip('/'))
        return {origin for origin in origins if origin}

    def _check_origin(self) -> Response | None:
        """Reject a browser request carrying a disallowed ``Origin``.

        Guards against DNS-rebinding as required by the Streamable HTTP transport.
        A request without an ``Origin`` header is not browser-initiated and passes.

        :return: a ``403`` response when the origin is rejected, otherwise ``None``.
        """
        if not (origin := request.httprequest.headers.get('Origin')):
            return None
        if origin.rstrip('/') in self._get_allowed_origins():
            return None
        allow_any = (
            request.env['ir.config_parameter']
            .sudo()
            .get_param(
                'muk_mcp.allow_any_origin',
                'False',
            )
        )
        if str2bool(allow_any, default=False):
            return None
        self._log_request(
            'origin_rejected',
            status='error',
            error_message=f'Rejected origin: {origin}',
        )
        return Response(status=403)

    def _get_meta_version(self, params: dict[str, Any]) -> str | None:
        """Return the protocol version carried in the request ``_meta``, if any."""
        meta = params.get('_meta')
        if not isinstance(meta, dict):
            return None
        value = meta.get(version.META_PROTOCOL_VERSION)
        return value if isinstance(value, str) else None

    def _resolve_profile(
        self,
        params: dict[str, Any],
        session: models.BaseModel | None = None,
        request_id: Any = None,
    ) -> tuple[ProtocolProfile | None, dict[str, Any] | None]:
        """Resolve the protocol profile governing this request.

        Takes the version from ``_meta`` first, then the ``MCP-Protocol-Version``
        header, then the version stored on ``session``. When both ``_meta`` and the
        header are present they must agree.

        :param session: the session named by the request, already resolved so the
            lookup is not repeated for every request.
        :return: a ``(profile, None)`` pair, or ``(None, error)`` with a JSON-RPC
            error when the version is contradictory or unsupported.
        """
        meta_version = self._get_meta_version(params)
        header_version = request.httprequest.headers.get(
            version.MCP_PROTOCOL_VERSION_HEADER,
        )
        if meta_version and header_version and meta_version != header_version:
            return None, protocol.make_jsonrpc_error(
                common.JSONRPC_INVALID_PARAMS,
                (
                    'Protocol version mismatch between the '
                    f'{version.MCP_PROTOCOL_VERSION_HEADER} header '
                    f'({header_version}) and the request _meta ({meta_version})'
                ),
                request_id=request_id,
            )
        if requested := meta_version or header_version:
            if not version.is_supported(requested):
                return None, protocol.make_unsupported_version_error(
                    requested,
                    request_id=request_id,
                )
            profile = version.get_profile(requested)
            if profile.stateless and not header_version:
                return None, protocol.make_jsonrpc_error(
                    common.JSONRPC_INVALID_PARAMS,
                    (
                        f'The {version.MCP_PROTOCOL_VERSION_HEADER} header is '
                        f'required on protocol revision {requested}'
                    ),
                    request_id=request_id,
                )
            return profile, None
        if session:
            return version.get_profile(session.protocol_version), None
        return version.get_profile(None), None

    def _check_required_meta(
        self,
        profile: ProtocolProfile,
        method: str,
        params: dict[str, Any],
        request_id: Any = None,
    ) -> dict[str, Any] | None:
        """Verify a stateless request carries the ``_meta`` fields it must.

        ``server/discover`` is held to the protocol version alone: it is the probe
        a client uses before it knows what the server speaks, and demanding the
        full block there would make discovery harder than the exchange it guards.

        :return: a JSON-RPC error when a required field is absent, else ``None``.
        """
        if not profile.stateless:
            return None
        required = [version.META_PROTOCOL_VERSION]
        if method != 'server/discover':
            required.append(version.META_CLIENT_CAPABILITIES)
        meta = params.get('_meta')
        meta = meta if isinstance(meta, dict) else {}
        if missing := [key for key in required if meta.get(key) is None]:
            return protocol.make_jsonrpc_error(
                common.JSONRPC_INVALID_PARAMS,
                f'Missing required _meta fields: {", ".join(missing)}',
                request_id=request_id,
            )
        return None

    def _get_header_profile(self) -> ProtocolProfile:
        """Return the profile for a bodyless request, from its version header."""
        return version.get_profile(
            request.httprequest.headers.get(version.MCP_PROTOCOL_VERSION_HEADER),
        )

    def _get_response_status(self, response_data: dict[str, Any]) -> int:
        """Return the HTTP status for a dispatched JSON-RPC response.

        A request naming a session the server no longer holds is answered ``404``:
        that is the transport's only signal telling a client to re-handshake, and
        without it a terminated session looks like an ordinary error the client
        has no mandate to recover from. Version faults are reported as ``400`` on
        every revision. The stateless revision additionally requires ``404`` for an
        unimplemented method; the stateful ones never did, so they keep answering
        ``200`` there. Every other outcome, including tool errors, rides on ``200``.
        """
        error = response_data.get('error')
        if not isinstance(error, dict):
            return 200
        if getattr(request, '_mcp_session_gone', False):
            return 404
        code = error.get('code')
        if code in (
            common.MCP_UNSUPPORTED_PROTOCOL_VERSION,
            common.JSONRPC_INVALID_PARAMS,
        ):
            return 400
        profile = getattr(request, '_mcp_profile', None)
        if code == common.JSONRPC_METHOD_NOT_FOUND and profile and profile.stateless:
            return 404
        return 200

    def _resolve_identity(
        self,
        profile: ProtocolProfile,
        session: models.BaseModel | None = None,
        request_id: Any = None,
    ) -> tuple[models.BaseModel | None, dict[str, Any] | None]:
        """Resolve the caller, by session for the stateful revisions or statelessly.

        Stateless callers carry no session; they are identified by the bearer key
        the ``mcp`` auth method already resolved onto the request.

        :param session: the session named by the request, already resolved.
        :return: a ``(session, None)`` pair with ``session`` empty for stateless
            callers, or ``(None, error)`` with a JSON-RPC error.
        """
        if profile.stateless:
            return None, None
        if not request.httprequest.headers.get('Mcp-Session-Id'):
            return None, protocol.make_jsonrpc_error(
                common.JSONRPC_INVALID_REQUEST,
                'Session required',
                request_id=request_id,
            )
        if not session:
            request._mcp_session_gone = True
            return None, protocol.make_jsonrpc_error(
                common.JSONRPC_INVALID_REQUEST,
                'Session not found',
                request_id=request_id,
            )
        if not session.initialized:
            return None, protocol.make_jsonrpc_error(
                common.JSONRPC_INVALID_REQUEST,
                'Session not initialized',
                request_id=request_id,
            )
        return session, None

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

    def _get_unauthenticated_methods(self, profile: ProtocolProfile) -> frozenset[str]:
        """Return the methods reachable without an established caller identity."""
        if profile.stateless:
            return frozenset({'server/discover'})
        return frozenset({'ping', 'initialize', 'notifications/initialized'})

    def _get_shared_handlers(self) -> dict[str, Any]:
        """Return the handlers every served protocol revision exposes."""
        return {
            'notifications/cancelled': lambda p: None,
            'tools/list': self._handle_tools_list,
            'tools/call': self._handle_tools_call,
            'resources/list': self._handle_resources_list,
            'resources/read': self._handle_resources_read,
            'resources/templates/list': self._handle_resource_templates_list,
            'prompts/list': self._handle_prompts_list,
            'prompts/get': self._handle_prompts_get,
            'completion/complete': self._handle_completion_complete,
        }

    def _get_handlers(self, profile: ProtocolProfile) -> dict[str, Any]:
        """Return the handler map for ``profile``.

        The stateless revision drops the handshake, ``ping``, ``logging/setLevel``
        and the roots notification, and adds ``server/discover`` in their place.
        """
        handlers = self._get_shared_handlers()
        if profile.stateless:
            handlers['server/discover'] = self._handle_discover
            return handlers
        handlers.update(
            {
                'ping': lambda p: {},
                'initialize': self._handle_initialize,
                'notifications/initialized': self._handle_initialized,
                'notifications/roots/list_changed': lambda p: None,
                'logging/setLevel': lambda p: {},
            },
        )
        return handlers

    def _dispatch_method(self, data: dict[str, Any]) -> dict[str, Any] | None:
        """Route one parsed JSON-RPC request to its handler and wrap the outcome.

        Resolves the protocol revision, then the caller — by session for the
        stateful revisions, from the bearer key for the stateless one — and maps
        handler exceptions to JSON-RPC errors.

        :return: a JSON-RPC response or error dict, or ``None`` for notifications
            (which produce no reply).
        """
        method, params, request_id = (
            data.get('method'),
            data.get('params') or {},
            data.get('id'),
        )
        session_id = request.httprequest.headers.get('Mcp-Session-Id')
        declared = self._get_meta_version(params) or request.httprequest.headers.get(
            version.MCP_PROTOCOL_VERSION_HEADER,
        )
        session = (
            self._get_session(session_id)
            if session_id and not version.get_profile(declared).stateless
            else None
        )
        profile, error = self._resolve_profile(
            params,
            session=session,
            request_id=request_id,
        )
        if error is not None:
            return error
        request._mcp_profile = profile
        handlers = self._get_handlers(profile)
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
        error = self._check_required_meta(
            profile, method, params, request_id=request_id
        )
        if error is not None:
            return error
        if method not in self._get_unauthenticated_methods(profile):
            _caller, error = self._resolve_identity(
                profile,
                session=session,
                request_id=request_id,
            )
            if error is not None:
                return error
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
        return protocol.make_jsonrpc_response(
            result, request_id=request_id, result_type=profile.result_type
        )

    def _handle_initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle ``initialize``: create a session and return the server capabilities.

        Stores the negotiated revision on the session so later requests that carry no
        ``MCP-Protocol-Version`` header are still served under the right profile, and
        stashes the new session id on the request for the ``Mcp-Session-Id`` header.
        """
        negotiated = version.negotiate_handshake(params.get('protocolVersion'))
        session = (
            request.env['muk_mcp.session']
            .sudo()
            .create(
                {
                    'user_id': request.env.uid,
                    'initialized': False,
                    'protocol_version': negotiated,
                },
            )
        )
        request._mcp_new_session_id = session.session_id
        return protocol.make_initialize_result(
            negotiated,
            capabilities=self._get_capabilities(
                params,
                version.get_profile(negotiated),
            ),
        )

    def _handle_discover(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle ``server/discover``: advertise served revisions and capabilities."""
        return protocol.make_discover_result(
            capabilities=self._get_capabilities(
                params,
                version.get_profile(version.MCP_VERSION_2026_07_28),
            ),
        )

    def _get_capabilities(
        self,
        params: dict[str, Any],
        profile: ProtocolProfile,
    ) -> dict[str, Any]:
        """Return the extra server capabilities advertised for ``profile``.

        The stateless revision has no server-initiated notification channel here, so
        the list-changed capabilities are withdrawn rather than advertised unserved.
        """
        if profile.stateless:
            return {
                'tools': {'listChanged': False},
                'prompts': {'listChanged': False},
                'resources': {'subscribe': False, 'listChanged': False},
            }
        return {}

    def _get_client_capabilities(self, params: dict[str, Any]) -> dict[str, Any] | None:
        """Return the capabilities the client declared, from the handshake or ``_meta``."""
        capabilities = params.get('capabilities')
        if isinstance(capabilities, dict):
            return capabilities
        meta = params.get('_meta')
        if isinstance(meta, dict):
            declared = meta.get(version.META_CLIENT_CAPABILITIES)
            if isinstance(declared, dict):
                return declared
        return None

    def _get_client_extension(
        self,
        params: dict[str, Any],
        extension_id: str,
    ) -> dict[str, Any] | None:
        """Return the settings the client declared for ``extension_id``, if any."""
        capabilities = self._get_client_capabilities(params)
        if not isinstance(capabilities, dict):
            return None
        offered = capabilities.get('extensions')
        if not isinstance(offered, dict):
            return None
        settings = offered.get(extension_id)
        return settings if isinstance(settings, dict) else None

    def _client_offers_extension(
        self,
        params: dict[str, Any],
        extension_id: str,
        profile: ProtocolProfile | None = None,
    ) -> bool:
        """Report whether the client declared support for ``extension_id``.

        On the session-based revisions a client that sends no extension map at all
        predates extension negotiation and is treated as accepting everything, so
        turning negotiation on never silently withdraws an extension from a client
        already in the field. The stateless revision has no such history -- it
        requires capabilities on every request and forbids inferring them -- so
        there an extension must be asked for explicitly.
        """
        capabilities = self._get_client_capabilities(params)
        offered = (
            capabilities.get('extensions') if isinstance(capabilities, dict) else None
        )
        if isinstance(offered, dict):
            return extension_id in offered
        return not (profile and profile.stateless)

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
        if not (uri := params.get('uri')):
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
        return request.env['muk_mcp.prompt'].get_prompt(
            params.get('name'),
            params.get('arguments') or {},
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
        """Serve a JSON-RPC request and return the reply.

        JSON-RPC batching was removed from the protocol in 2025-06-18, so an array
        body is rejected rather than dispatched.

        :return: a JSON response, a 202 for notifications, a 403 for a rejected
            origin, or a 429 when rate limited; a freshly created session id is
            echoed in the ``Mcp-Session-Id`` header.
        """
        if error := self._check_origin():
            return error
        if request.params.get('jsonrpc_batch') is not None:
            return request.make_json_response(
                protocol.make_jsonrpc_error(
                    common.JSONRPC_INVALID_REQUEST,
                    'Invalid Request: JSON-RPC batching is not supported',
                ),
                status=400,
            )
        if not self._check_rate_limit():
            return request.make_json_response(
                protocol.make_jsonrpc_error(
                    common.JSONRPC_INTERNAL_ERROR,
                    'Rate limit exceeded',
                ),
                status=429,
            )
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
        return request.make_json_response(
            response_data,
            status=self._get_response_status(response_data),
            headers=headers,
        )

    @mcp_route('/mcp', methods=['GET'])
    def mcp_get(self, **kw: Any) -> Response:
        """Open the SSE notification stream for a session, supporting ``Last-Event-ID`` resume.

        The stateless revision removes the GET endpoint entirely, so a client
        declaring it is answered ``405`` rather than served a session stream.

        :return: a ``text/event-stream`` response, or 405 when SSE is not requested.
        """
        if error := self._check_origin():
            return error
        if self._get_header_profile().stateless:
            return Response(status=405)
        if 'text/event-stream' not in request.httprequest.headers.get('Accept', ''):
            return Response(status=405)
        session, error = self._require_session()
        if error:
            return error
        after_id = 0
        if last_event_id := request.httprequest.headers.get('Last-Event-ID'):
            if resume := request.env['muk_mcp.notification'].search(
                [
                    ('event_id', '=', last_event_id),
                    ('session_id', '=', session.id),
                ],
                limit=1,
            ):
                after_id = resume.id
        return self._make_sse_response(
            self._claim_notifications(session.id, after_id),
        )

    @mcp_route('/mcp', methods=['DELETE'])
    def mcp_delete(self, **kw: Any) -> Response:
        """Terminate the session named in the request header by deactivating it.

        The stateless revision has no sessions to terminate and is answered ``405``.
        """
        if error := self._check_origin():
            return error
        if self._get_header_profile().stateless:
            return Response(status=405)
        if session := self._get_session(
            request.httprequest.headers.get('Mcp-Session-Id'),
        ):
            session.write({'active': False})
        return Response(status=200)
