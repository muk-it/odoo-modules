from __future__ import annotations

import json
from typing import Any

from odoo import api
from odoo.tests import tagged
from odoo.tests.common import new_test_user

from odoo.addons.muk_mcp.core.tool import invalidate_registry_cache, mcp_tool
from odoo.addons.muk_mcp.tests.common import MCPHttpCase


@api.model
@mcp_tool(
    name='mcp_auth_probe',
    description='Report the authenticated user and the MCP context annotation.',
    input_schema={'type': 'object', 'properties': {}},
    category='read',
)
def _mcp_auth_probe(self):
    return {
        'uid': self.env.uid,
        'login': self.env.user.login,
        'mcp_name': self.env.context.get('mcp_name'),
    }


@tagged('post_install', '-at_install')
class TestMcpAuth(MCPHttpCase):
    """Cover the ``mcp`` bearer-token auth method guarding the ``/mcp`` routes."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.config = cls.env['ir.config_parameter'].sudo()
        cls.mixin_cls = type(cls.env['muk_mcp.mixin'])
        cls.mixin_cls._mcp_auth_probe = _mcp_auth_probe
        invalidate_registry_cache(cls.env)

    @classmethod
    def tearDownClass(cls) -> None:
        delattr(cls.mixin_cls, '_mcp_auth_probe')
        invalidate_registry_cache(cls.env)
        super().tearDownClass()

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _probe(self, token: str | None = None) -> dict[str, Any]:
        """Run the auth probe tool over a fresh session and return its payload."""
        session_id = self.mcp_handshake(token=token)
        body = self.mcp_call_tool(
            'mcp_auth_probe',
            {},
            session_id=session_id,
            token=token,
        )
        return json.loads(body['result']['content'][0]['text'])

    # ----------------------------------------------------------
    # Tests: rejected credentials
    # ----------------------------------------------------------

    def test_missing_authorization_header_is_unauthorized(self):
        response = self.mcp_post(
            {'jsonrpc': '2.0', 'id': 1, 'method': 'ping'}, token=False
        )
        self.assertEqual(response.status_code, 401)

    def test_basic_authorization_scheme_is_unauthorized(self):
        response = self.mcp_post(
            {'jsonrpc': '2.0', 'id': 1, 'method': 'ping'},
            headers={'Authorization': 'Basic abc'},
        )
        self.assertEqual(response.status_code, 401)

    def test_bare_token_without_scheme_is_unauthorized(self):
        response = self.mcp_post(
            {'jsonrpc': '2.0', 'id': 1, 'method': 'ping'},
            headers={'Authorization': self.mcp_token},
        )
        self.assertEqual(response.status_code, 401)

    def test_empty_bearer_token_is_unauthorized(self):
        for header in ('Bearer', 'Bearer ', 'Bearer    '):
            response = self.mcp_post(
                {'jsonrpc': '2.0', 'id': 1, 'method': 'ping'},
                headers={'Authorization': header},
            )
            self.assertEqual(response.status_code, 401, header)

    def test_unknown_token_is_unauthorized(self):
        response = self.mcp_post(
            {'jsonrpc': '2.0', 'id': 1, 'method': 'ping'},
            token='this-token-does-not-exist',
        )
        self.assertEqual(response.status_code, 401)

    def test_archived_key_is_unauthorized(self):
        token, key = self.make_mcp_key(self.mcp_user, name='Archived Key')
        response = self.mcp_post(self.mcp_ping(), token=token)
        self.assertEqual(response.status_code, 200)
        key.write({'active': False})
        response = self.mcp_post(self.mcp_ping(), token=token)
        self.assertEqual(response.status_code, 401)

    # ----------------------------------------------------------
    # Tests: accepted credentials
    # ----------------------------------------------------------

    def test_bearer_scheme_is_case_insensitive(self):
        for scheme in ('bearer', 'BEARER', 'BeArEr'):
            response = self.mcp_post(
                {'jsonrpc': '2.0', 'id': 1, 'method': 'ping'},
                headers={'Authorization': '%s %s' % (scheme, self.mcp_token)},
            )
            self.assertEqual(response.status_code, 200, scheme)
            self.assertEqual(response.json()['result'], {}, scheme)

    def test_valid_key_switches_the_request_user(self):
        result = self._probe()
        self.assertEqual(result['uid'], self.mcp_user.id)
        self.assertEqual(result['login'], self.mcp_user.login)

    def test_key_of_another_user_switches_to_that_user(self):
        other = new_test_user(
            self.env, login='mcp_auth_second', groups='base.group_user'
        )
        token, _key = self.make_mcp_key(other, name='Second User Key')
        result = self._probe(token=token)
        self.assertEqual(result['uid'], other.id)

    # ----------------------------------------------------------
    # Tests: context annotation
    # ----------------------------------------------------------

    def test_annotation_puts_the_key_name_in_the_context(self):
        self.config.set_param('muk_mcp.annotate_messages', 'True')
        self.assertEqual(self._probe()['mcp_name'], self.mcp_key.name)

    def test_annotation_can_be_disabled(self):
        self.config.set_param('muk_mcp.annotate_messages', 'False')
        self.assertIsNone(self._probe()['mcp_name'])

    # ----------------------------------------------------------
    # Tests: CORS preflight
    # ----------------------------------------------------------

    def test_options_preflight_skips_authentication(self):
        response = self.url_open('/mcp', method='OPTIONS')
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.headers['Access-Control-Allow-Origin'], '*')
        self.assertIn(
            'authorization',
            response.headers['Access-Control-Allow-Headers'],
        )
        self.assertIn(
            'mcp-session-id',
            response.headers['Access-Control-Expose-Headers'],
        )
