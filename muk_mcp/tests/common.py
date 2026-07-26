from __future__ import annotations

import json
import secrets
from typing import Any

from requests import Response

from odoo import models
from odoo.tests import HttpCase
from odoo.tests.common import new_test_user


class MCPHttpCase(HttpCase):
    """Base HTTP case issuing authenticated JSON-RPC calls against ``/mcp``."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.mcp_user = new_test_user(
            cls.env,
            login='mcp_http_user',
            groups='base.group_user',
        )
        cls.mcp_token, cls.mcp_key = cls.make_mcp_key(cls.mcp_user)

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @classmethod
    def make_mcp_key(
        cls,
        user: models.BaseModel,
        name: str = 'HTTP Test Key',
        scope: str = 'write',
        rate_limit: int = 0,
        active: bool = True,
    ) -> tuple[str, models.BaseModel]:
        """Create an MCP key for ``user`` and return its plaintext and record.

        :param rate_limit: per-minute budget; ``0`` disables rate limiting.
        """
        raw_key = secrets.token_urlsafe(32)
        key_model = cls.env['muk_mcp.key']
        record = key_model.create(
            {
                'name': name,
                'user_id': user.id,
                'key_hash': key_model._hash_key(raw_key),
                'key_prefix': raw_key[:8],
                'scope': scope,
                'rate_limit': rate_limit,
                'active': active,
            },
        )
        return raw_key, record

    def mcp_headers(
        self,
        token: str | bool | None = None,
        session_id: str | None = None,
        headers: dict[str, str] | None = None,
        content_type: str | None = 'application/json',
    ) -> dict[str, str]:
        """Build the headers for an ``/mcp`` call.

        :param token: bearer token to send; ``None`` uses the default test key
            and ``False`` omits the ``Authorization`` header entirely.
        :param headers: extra headers merged last, so they win over the defaults.
        """
        result = {}
        if content_type:
            result['Content-Type'] = content_type
        if token is not False:
            result['Authorization'] = 'Bearer %s' % (token or self.mcp_token)
        if session_id:
            result['Mcp-Session-Id'] = session_id
        result.update(headers or {})
        return result

    def mcp_ping(self, request_id: int = 1) -> dict[str, Any]:
        """Return a minimal ``ping`` JSON-RPC request body."""
        return {'jsonrpc': '2.0', 'id': request_id, 'method': 'ping'}

    def mcp_post(
        self,
        payload: Any = None,
        body: str | None = None,
        **kwargs: Any,
    ) -> Response:
        """POST a JSON-RPC ``payload``, or the raw ``body`` when given, to ``/mcp``."""
        return self.url_open(
            '/mcp',
            data=body if body is not None else json.dumps(payload),
            headers=self.mcp_headers(**kwargs),
        )

    def mcp_json(self, payload: Any = None, **kwargs: Any) -> Any:
        """POST a JSON-RPC payload to ``/mcp`` and return the decoded response body."""
        return self.mcp_post(payload, **kwargs).json()

    def mcp_get(self, **kwargs: Any) -> Response:
        """Send a ``GET /mcp`` request with the given MCP headers."""
        kwargs.setdefault('content_type', None)
        return self.url_open(
            '/mcp',
            headers=self.mcp_headers(**kwargs),
            method='GET',
        )

    def mcp_delete(self, **kwargs: Any) -> Response:
        """Send a ``DELETE /mcp`` request with the given MCP headers."""
        kwargs.setdefault('content_type', None)
        return self.url_open(
            '/mcp',
            headers=self.mcp_headers(**kwargs),
            method='DELETE',
        )

    def mcp_handshake(self, token: str | bool | None = None) -> str:
        """Run ``initialize`` plus ``notifications/initialized`` and return the session id."""
        response = self.mcp_post(
            {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {}},
            token=token,
        )
        session_id = response.headers['Mcp-Session-Id']
        self.mcp_post(
            {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
            token=token,
            session_id=session_id,
        )
        return session_id

    def mcp_call_tool(
        self,
        name: str | None = None,
        arguments: Any = None,
        session_id: str | None = None,
        token: str | bool | None = None,
    ) -> Any:
        """Invoke ``tools/call`` over HTTP and return the decoded JSON-RPC body."""
        params = {}
        if name is not None:
            params['name'] = name
        if arguments is not None:
            params['arguments'] = arguments
        return self.mcp_json(
            {
                'jsonrpc': '2.0',
                'id': 10,
                'method': 'tools/call',
                'params': params,
            },
            token=token,
            session_id=session_id,
        )
