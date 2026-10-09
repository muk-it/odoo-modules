from __future__ import annotations

import json
from typing import Any

from requests import Response

from odoo import models
from odoo.api import Environment
from odoo.tests import HttpCase, TransactionCase, new_test_user

from odoo.addons.muk_mcp.tools import version
from odoo.addons.muk_mcp.tools.common import MCP_ENDPOINT

PNG = (
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQ'
    'VQYV2NgAAIAAAUAAarVyFEAAAAASUVORK5CYII='
)


def make_mcp_key(
    user: models.BaseModel,
    scope: str = 'write',
    rate_limit: int = 0,
) -> tuple[str, models.BaseModel]:
    """Generate a key owned by ``user`` and return its plaintext and record."""
    record, token = (
        user.env['muk_mcp.key']
        .with_user(user)
        ._generate(
            f'Key of {user.login}',
            scope,
            rate_limit,
        )
    )
    return token, user.env['muk_mcp.key'].browse(record.id)


def run_tool(
    env: Environment,
    name: str,
    arguments: dict[str, Any] | None,
    scope: str | None = None,
) -> Any:
    """Run tool ``name`` in ``env`` and return its result, JSON-decoded if text."""
    result, _info = env['muk_mcp.tool']._call(name, arguments, env, enforce_scope=scope)
    return json.loads(result) if isinstance(result, str) else result


class MCPLogMixin:
    """Read the audit entries a test wrote, whatever the database held before."""

    def setUp(self) -> None:
        """Remember the newest audit entry before the test runs."""
        super().setUp()
        self.log_floor = (
            self.env['muk_mcp.log'].sudo().search([], order='id desc', limit=1).id or 0
        )

    def logs(self, domain: list) -> models.BaseModel:
        """Return the audit entries matching ``domain`` that this test wrote."""
        return (
            self.env['muk_mcp.log']
            .sudo()
            .search([*domain, ('id', '>', self.log_floor)])
        )


class MCPToolCase(MCPLogMixin, TransactionCase):
    """Base case running MCP tools in-process, auditing on the test cursor."""

    @classmethod
    def setUpClass(cls) -> None:
        """Route the audit log's own cursor into the test transaction."""
        super().setUpClass()
        cls.enterClassContext(cls.registry_test_mode())

    def call_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
        user: models.BaseModel | None = None,
        scope: str | None = None,
    ) -> Any:
        """Run tool ``name`` as ``user`` and return its result, JSON-decoded if text."""
        return run_tool(
            self.env(user=user) if user else self.env, name, arguments, scope
        )


class MCPHttpCase(MCPLogMixin, HttpCase):
    """Base case posting authenticated JSON-RPC requests to the MCP endpoint."""

    @classmethod
    def setUpClass(cls) -> None:
        """Create the internal user and the key every request authenticates with."""
        super().setUpClass()
        cls.mcp_user = new_test_user(
            cls.env,
            login='mcp_http_user',
            groups='base.group_user,base.group_partner_manager',
        )
        cls.mcp_token, cls.mcp_key = make_mcp_key(cls.mcp_user)

    def mcp_post(
        self,
        payload: Any = None,
        body: str | None = None,
        token: str | bool | None = None,
        headers: dict[str, str | None] | None = None,
    ) -> Response:
        """POST ``payload`` as JSON, the raw ``body``, or nothing to the MCP endpoint.

        :param token: bearer token; ``None`` sends the test key, ``False`` none.
        :param headers: merged over the defaults; a ``None`` value drops a header.
        """
        merged = {'Content-Type': 'application/json'}
        if token is not False:
            merged['Authorization'] = f'Bearer {token or self.mcp_token}'
        merged.update(headers or {})
        return self.url_open(
            MCP_ENDPOINT,
            data=json.dumps(payload) if payload is not None else body,
            headers={key: value for key, value in merged.items() if value is not None},
            method='POST',
        )

    def mcp_call(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Response:
        """Send a handshake-era request for ``method``, without any ``_meta``."""
        return self.mcp_post(
            {'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params or {}},
            **kwargs,
        )

    def mcp_tool(
        self,
        name: str,
        arguments=None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Call tool ``name`` on the handshake era and return the ``tools/call`` result."""
        response = self.mcp_call(
            'tools/call',
            {'name': name, 'arguments': arguments or {}},
            **kwargs,
        )
        return response.json()['result']

    def mcp_meta(self, capabilities: dict[str, Any] | None = None) -> dict[str, Any]:
        """Build the ``_meta`` block a stateless request carries."""
        return {
            version.META_PROTOCOL_VERSION: version.MCP_STATELESS_VERSION,
            version.META_CLIENT_INFO: {'name': 'muk_mcp.tests', 'version': '1.0'},
            version.META_CLIENT_CAPABILITIES: capabilities or {},
        }

    def mcp_stateless_post(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        meta: dict[str, Any] | None = None,
        headers: dict[str, str | None] | None = None,
        **kwargs: Any,
    ) -> Response:
        """POST a stateless request with its ``_meta`` block and mirrored headers.

        :param meta: replaces the default ``_meta`` block.
        :param headers: merged over the required headers; ``None`` drops one.
        """
        params = {**(params or {}), '_meta': self.mcp_meta() if meta is None else meta}
        required = {
            version.MCP_PROTOCOL_VERSION_HEADER: version.MCP_STATELESS_VERSION,
            version.MCP_METHOD_HEADER: method,
        }
        if method in version.MCP_NAME_METHODS:
            required[version.MCP_NAME_HEADER] = params.get('name') or params.get('uri')
        return self.mcp_post(
            {'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params},
            headers={**required, **(headers or {})},
            **kwargs,
        )
