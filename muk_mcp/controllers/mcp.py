from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from odoo import http, models
from odoo.exceptions import ConcurrencyError, UserError
from odoo.http import Response, request
from odoo.sql_db import PG_CONCURRENCY_EXCEPTIONS_TO_RETRY
from odoo.tools import config

from odoo.addons.muk_mcp.tools import common, protocol, version
from odoo.addons.muk_mcp.tools.exception import (
    MCPResourceNotFound,
)


class MCPController(http.Controller):
    """Serve the MCP Streamable HTTP transport, statelessly, on every revision."""

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
            self._log_request('rate_limited', status='rate_limited')
            return False
        return True

    def _log_request(self, method: str, **kwargs: Any) -> None:
        """Write an MCP audit-log row for the request when logging is enabled."""
        if config.get('mcp_logging', True):
            request.env['muk_mcp.log'].log(
                user_id=request.env.uid, method=method, **kwargs
            )

    def _get_tool_enforce_scope(self) -> str | None:
        """Return the scope to enforce on tool calls, derived from the API key."""
        key = getattr(request, '_mcp_key', None)
        return key.scope if key else None

    def _check_origin(self) -> bool:
        """Report whether a browser request's ``Origin`` is allowed.

        Guards against DNS rebinding. The allow-list is server configuration
        only, because a rebound request carries the attacker's name as ``Host``.
        """
        if not (origin := request.httprequest.headers.get('Origin')):
            return True
        param = request.env['ir.config_parameter'].sudo()
        configured = param.get_str('muk_mcp.allowed_origins')
        allowed = {entry.strip().rstrip('/') for entry in configured.split(',')}
        allowed.add(param.get_str('web.base.url').rstrip('/'))
        if origin.rstrip('/') in allowed - {''}:
            return True
        if param.get_bool('muk_mcp.allow_any_origin'):
            return True
        self._log_request(
            'origin_rejected',
            status='error',
            error_message=f'Rejected origin: {origin}',
        )
        return False

    def _resolve_version(
        self,
        params: dict[str, Any],
        request_id: Any = None,
    ) -> tuple[str | None, dict[str, Any] | None]:
        """Resolve the protocol revision, from ``_meta`` or the version header.

        Both must agree; a request carrying neither is a handshake-era request.

        :return: ``(version, None)``, or ``(None, error)`` with a JSON-RPC error.
        """
        meta = params.get('_meta')
        meta_version = (
            meta.get(version.META_PROTOCOL_VERSION) if isinstance(meta, dict) else None
        )
        header_version = request.httprequest.headers.get(
            version.MCP_PROTOCOL_VERSION_HEADER,
        )
        if meta_version and header_version and meta_version != header_version:
            return None, protocol.make_jsonrpc_error(
                common.MCP_HEADER_MISMATCH,
                (
                    f'Protocol version mismatch between the '
                    f'{version.MCP_PROTOCOL_VERSION_HEADER} header '
                    f'({header_version}) and the request _meta ({meta_version})'
                ),
                request_id=request_id,
            )
        requested = meta_version or header_version
        if not requested:
            return version.MCP_HANDSHAKE_VERSIONS[0], None
        if requested not in version.MCP_SUPPORTED_VERSIONS:
            return None, protocol.make_jsonrpc_error(
                common.MCP_UNSUPPORTED_PROTOCOL_VERSION,
                f'Unsupported protocol version: {requested}',
                data={
                    'supported': list(version.MCP_SUPPORTED_VERSIONS),
                    'requested': requested,
                },
                request_id=request_id,
            )
        if requested == version.MCP_STATELESS_VERSION and not header_version:
            return None, protocol.make_jsonrpc_error(
                common.MCP_HEADER_MISMATCH,
                (
                    f'The {version.MCP_PROTOCOL_VERSION_HEADER} header is '
                    f'required on protocol revision {requested}'
                ),
                request_id=request_id,
            )
        return requested, None

    def _check_stateless_request(
        self,
        method: str,
        params: dict[str, Any],
        request_id: Any = None,
    ) -> dict[str, Any] | None:
        """Verify the ``_meta`` fields and mirrored headers the stateless revision requires.

        ``server/discover``, the client's first probe, needs the version alone.

        :return: a JSON-RPC error when something required is absent, else ``None``.
        """
        meta = params.get('_meta')
        meta = meta if isinstance(meta, dict) else {}
        required = [version.META_PROTOCOL_VERSION]
        if method != 'server/discover':
            required.append(version.META_CLIENT_CAPABILITIES)
        if missing := [key for key in required if meta.get(key) is None]:
            return protocol.make_jsonrpc_error(
                common.JSONRPC_INVALID_PARAMS,
                f'Missing required _meta fields: {", ".join(missing)}',
                request_id=request_id,
            )
        headers = request.httprequest.headers
        expected = [version.MCP_METHOD_HEADER]
        if method in version.MCP_NAME_METHODS:
            expected.append(version.MCP_NAME_HEADER)
        if missing := [header for header in expected if header not in headers]:
            return protocol.make_jsonrpc_error(
                common.MCP_HEADER_MISMATCH,
                f'Missing required headers: {", ".join(missing)}',
                request_id=request_id,
            )
        return None

    def _check_mirrored_headers(
        self,
        method: str,
        params: dict[str, Any],
        request_id: Any = None,
    ) -> dict[str, Any] | None:
        """Verify the ``Mcp-Method`` and ``Mcp-Name`` headers agree with the body.

        Intermediaries route on them without reading the body.

        :return: a JSON-RPC error when a header contradicts the body, else ``None``.
        """
        headers = request.httprequest.headers
        mirrored = [(version.MCP_METHOD_HEADER, method)]
        if method in version.MCP_NAME_METHODS:
            mirrored.append(
                (version.MCP_NAME_HEADER, params.get('name') or params.get('uri')),
            )
        for header, expected in mirrored:
            sent = headers.get(header)
            if sent is not None and version.decode_header_value(sent) != expected:
                return protocol.make_jsonrpc_error(
                    common.MCP_HEADER_MISMATCH,
                    f'Header mismatch: the {header} header does not match the body',
                    request_id=request_id,
                )
        return None

    def _get_response_status(
        self,
        response_data: dict[str, Any],
        protocol_version: str | None,
    ) -> int:
        """Return the HTTP status for a dispatched JSON-RPC response.

        Version, header and parameter faults are ``400``. The stateless revision
        also answers an unknown method with ``404``; every other outcome,
        including tool errors, rides on ``200``.
        """
        error = response_data.get('error')
        if not isinstance(error, dict):
            return 200
        code = error.get('code')
        if code in (
            common.MCP_UNSUPPORTED_PROTOCOL_VERSION,
            common.MCP_HEADER_MISMATCH,
            common.JSONRPC_INVALID_PARAMS,
        ):
            return 400
        if (
            code == common.JSONRPC_METHOD_NOT_FOUND
            and protocol_version == version.MCP_STATELESS_VERSION
        ):
            return 404
        return 200

    def _get_handlers(self, protocol_version: str) -> dict[str, Callable]:
        """Return the method handlers served on ``protocol_version``.

        The handshake revisions add ``initialize`` and ``ping``; the stateless
        revision replaces them with ``server/discover``.
        """
        handlers = {
            'tools/list': self._handle_tools_list,
            'tools/call': self._handle_tools_call,
            'resources/list': self._handle_resources_list,
            'resources/read': self._handle_resources_read,
            'resources/templates/list': self._handle_resource_templates_list,
            'prompts/list': self._handle_prompts_list,
            'prompts/get': self._handle_prompts_get,
            'completion/complete': self._handle_completion_complete,
        }
        if protocol_version == version.MCP_STATELESS_VERSION:
            handlers['server/discover'] = self._handle_discover
        else:
            handlers['initialize'] = self._handle_initialize
            handlers['ping'] = lambda params: {}
        return handlers

    def _dispatch_method(
        self,
        data: dict[str, Any],
    ) -> tuple[dict[str, Any], str | None]:
        """Route one JSON-RPC request to its handler and wrap the outcome.

        :return: the JSON-RPC response or error, and the revision it was served on.
        """
        method, params, request_id = (
            data['method'],
            data.get('params') or {},
            data.get('id'),
        )
        protocol_version, error = self._resolve_version(params, request_id=request_id)
        if error is not None:
            return error, None
        if protocol_version == version.MCP_STATELESS_VERSION:
            error = self._check_stateless_request(method, params, request_id=request_id)
        error = error or self._check_mirrored_headers(
            method,
            params,
            request_id=request_id,
        )
        if error is not None:
            return error, protocol_version
        if not (handler := self._get_handlers(protocol_version).get(method)):
            self._log_request(
                method,
                status='error',
                error_message=f'Method not found: {method}',
            )
            return protocol.make_jsonrpc_error(
                common.JSONRPC_METHOD_NOT_FOUND,
                f'Method not found: {method}',
                request_id=request_id,
            ), protocol_version
        start = time.time()
        try:
            result = handler(params)
        except MCPResourceNotFound:
            return protocol.make_jsonrpc_error(
                common.JSONRPC_INVALID_PARAMS,
                'Resource not found',
                data={'uri': params.get('uri') or ''},
                request_id=request_id,
            ), protocol_version
        except (*PG_CONCURRENCY_EXCEPTIONS_TO_RETRY, ConcurrencyError):
            raise
        except UserError as exc:
            return protocol.make_jsonrpc_error(
                common.JSONRPC_INVALID_PARAMS,
                str(exc),
                request_id=request_id,
            ), protocol_version
        except Exception as exc:
            self._log_request(
                method,
                status='error',
                error_message=str(exc),
                duration_ms=int((time.time() - start) * 1000),
            )
            return protocol.make_jsonrpc_error(
                common.JSONRPC_INTERNAL_ERROR,
                protocol.format_internal_error(exc),
                request_id=request_id,
            ), protocol_version
        return protocol.make_jsonrpc_response(
            protocol.make_result_envelope(result, protocol_version, method),
            request_id=request_id,
        ), protocol_version

    def _get_capabilities(
        self,
        params: dict[str, Any],
        protocol_version: str,
    ) -> dict[str, Any]:
        """Return extra server capabilities to advertise on ``protocol_version``."""
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
        capabilities = self._get_client_capabilities(params) or {}
        offered = capabilities.get('extensions')
        settings = offered.get(extension_id) if isinstance(offered, dict) else None
        return settings if isinstance(settings, dict) else None

    def _client_offers_extension(
        self,
        params: dict[str, Any],
        extension_id: str,
        protocol_version: str,
    ) -> bool:
        """Report whether the client declared support for ``extension_id``.

        A handshake-era client without any extension map predates negotiation
        and accepts everything; a stateless client must ask explicitly.
        """
        capabilities = self._get_client_capabilities(params) or {}
        offered = capabilities.get('extensions')
        if isinstance(offered, dict):
            return extension_id in offered
        return protocol_version != version.MCP_STATELESS_VERSION

    def _handle_initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle ``initialize``: negotiate a revision and return the capabilities."""
        negotiated = version.negotiate_handshake(params.get('protocolVersion'))
        return protocol.make_initialize_result(
            negotiated,
            capabilities=self._get_capabilities(params, negotiated),
        )

    def _handle_discover(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle ``server/discover``: advertise the revision and capabilities."""
        return protocol.make_discover_result(
            capabilities=self._get_capabilities(params, version.MCP_STATELESS_VERSION),
        )

    def _handle_tools_list(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle ``tools/list``: return the tools registered for the ``mcp`` registry."""
        return {'tools': request.env['muk_mcp.tool'].sudo().get_tools(registry='mcp')}

    def _handle_tools_call(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle ``tools/call``: run the named tool, enforcing the API key scope."""
        if not (tool_name := params.get('name')):
            return protocol.make_tool_result(
                [protocol.make_text_content('Tool name is required')],
                is_error=True,
            )
        return request.env['muk_mcp.tool']._call_result(
            tool_name,
            params.get('arguments', {}),
            request.env,
            enforce_scope=self._get_tool_enforce_scope(),
        )

    def _handle_resources_list(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle ``resources/list``: no concrete resources are enumerated (templates only)."""
        return {'resources': []}

    def _handle_resources_read(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle ``resources/read``: resolve the URI to content or report it missing.

        An empty ``contents`` array reads as a resource that exists and is blank,
        so an unresolvable or forbidden URI is answered as not found.
        """
        if not (uri := params.get('uri')):
            raise MCPResourceNotFound
        if not (entry := request.env['muk_mcp.mixin']._dispatch_resources_read(uri)):
            raise MCPResourceNotFound
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
        return {'prompts': request.env['muk_mcp.prompt'].sudo().get_prompts()}

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

    @http.route(
        common.MCP_ENDPOINT,
        type='http',
        auth='mcp',
        methods=['POST'],
        csrf=False,
        save_session=False,
        cors='*',
    )
    def mcp(self, **kw: Any) -> Response:
        """Serve one JSON-RPC message posted to the MCP endpoint.

        :return: the JSON-RPC reply, ``202`` for a notification, ``403`` for a
            rejected origin or ``429`` when rate limited.
        """
        raw_body = request.httprequest.get_data()
        if not self._check_origin():
            return Response(status=403)
        if not self._check_rate_limit():
            return request.make_json_response(
                protocol.make_jsonrpc_error(
                    common.JSONRPC_INTERNAL_ERROR,
                    'Rate limit exceeded',
                ),
                status=429,
            )
        data, error = protocol.parse_jsonrpc_request(raw_body)
        if error is not None:
            return request.make_json_response(error, status=400)
        if 'id' not in data:
            return Response(status=202)
        response_data, protocol_version = self._dispatch_method(data)
        return request.make_json_response(
            response_data,
            status=self._get_response_status(response_data, protocol_version),
        )
