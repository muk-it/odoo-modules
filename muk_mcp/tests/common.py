import json
import secrets

from odoo.tests import HttpCase
from odoo.tests.common import new_test_user

from odoo.addons.muk_mcp.tools import version


class MCPHttpCase(HttpCase):
    """Base HTTP case issuing authenticated JSON-RPC calls against ``/mcp``."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.key_model = cls.env['muk_mcp.key']
        cls.session_model = cls.env['muk_mcp.session']
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
    def make_mcp_key(cls, user, name='HTTP Test Key', scope='write', rate_limit=0):
        """Create an MCP key for ``user`` and return its raw token and record.

        :return: a ``(token, key)`` pair; the token is only available here, as the
            model stores nothing but its hash.
        """
        token = secrets.token_urlsafe(32)
        key = cls.env['muk_mcp.key'].sudo().create({
            'name': name,
            'user_id': user.id,
            'key_hash': cls.env['muk_mcp.key']._hash_key(token),
            'key_prefix': token[:8],
            'scope': scope,
            'rate_limit': rate_limit,
        })
        return token, key

    def mcp_headers(
        self,
        token=None,
        session_id=None,
        headers=None,
        content_type='application/json',
        protocol_version=None,
    ):
        """Build the headers for an ``/mcp`` call.

        :param token: bearer token to send; ``None`` uses the default test key
            and ``False`` omits the ``Authorization`` header entirely.
        :param protocol_version: value for the ``MCP-Protocol-Version`` header.
        :param headers: extra headers merged last, so they win over the defaults.
        """
        result = {}
        if content_type:
            result['Content-Type'] = content_type
        if token is not False:
            result['Authorization'] = 'Bearer %s' % (token or self.mcp_token)
        if session_id:
            result['Mcp-Session-Id'] = session_id
        if protocol_version:
            result[version.MCP_PROTOCOL_VERSION_HEADER] = protocol_version
        result.update(headers or {})
        return result

    def mcp_post(self, body, **kwargs):
        """POST a JSON-RPC body to ``/mcp`` and return the raw response."""
        return self.url_open(
            '/mcp',
            data=json.dumps(body),
            headers=self.mcp_headers(**kwargs),
        )

    def mcp_json(self, body, **kwargs):
        """POST a JSON-RPC body to ``/mcp`` and return the decoded reply."""
        return self.mcp_post(body, **kwargs).json()

    def mcp_get(self, **kwargs):
        """Issue a GET against ``/mcp`` and return the raw response."""
        return self.opener.get(
            '%s/mcp' % self.base_url(),
            headers=self.mcp_headers(content_type=None, **kwargs),
            timeout=30,
        )

    def mcp_delete(self, **kwargs):
        """Issue a DELETE against ``/mcp`` and return the raw response."""
        return self.opener.delete(
            '%s/mcp' % self.base_url(),
            headers=self.mcp_headers(content_type=None, **kwargs),
            timeout=30,
        )

    def mcp_ping(self, request_id=1):
        """Return a minimal ``ping`` JSON-RPC request body."""
        return {'jsonrpc': '2.0', 'id': request_id, 'method': 'ping'}

    def mcp_meta(
        self,
        protocol_version=version.MCP_VERSION_2026_07_28,
        client_info=None,
        capabilities=None,
        full=True,
    ):
        """Build the ``_meta`` block a stateless request carries.

        :param full: when ``False`` only the protocol version is included, which is
            all ``server/discover`` requires.
        """
        meta = {version.META_PROTOCOL_VERSION: protocol_version}
        if full:
            meta[version.META_CLIENT_INFO] = client_info or {
                'name': 'muk_mcp.tests',
                'version': '1.0',
            }
            meta[version.META_CLIENT_CAPABILITIES] = (
                capabilities if capabilities is not None else {}
            )
        return meta

    def mcp_stateless_post(
        self,
        method,
        params=None,
        request_id=1,
        protocol_version=version.MCP_VERSION_2026_07_28,
        send_header=True,
        meta=None,
        **kwargs,
    ):
        """POST a stateless JSON-RPC request carrying the required ``_meta`` block."""
        body_params = dict(params or {})
        body_params['_meta'] = (
            meta
            if meta is not None
            else self.mcp_meta(protocol_version=protocol_version)
        )
        kwargs.setdefault(
            'protocol_version',
            protocol_version if send_header else None,
        )
        return self.mcp_post(
            {
                'jsonrpc': '2.0',
                'id': request_id,
                'method': method,
                'params': body_params,
            },
            **kwargs,
        )

    def mcp_handshake(self, token=None, protocol_version=None):
        """Run ``initialize`` plus ``notifications/initialized`` and return the session id.

        :param protocol_version: revision to request; omitted leaves the server on
            its default.
        """
        params = {'protocolVersion': protocol_version} if protocol_version else {}
        response = self.mcp_post(
            {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': params},
            token=token,
        )
        session_id = response.headers['Mcp-Session-Id']
        self.mcp_post(
            {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
            token=token,
            session_id=session_id,
        )
        return session_id
