from __future__ import annotations

import base64

from odoo.tests import TransactionCase
from odoo.tools import BinaryBytes

from odoo.addons.muk_mcp.controllers.mcp import MCPController
from odoo.addons.muk_mcp.tests.common import MCPHttpCase
from odoo.addons.muk_mcp.tools import version

HANDSHAKE = version.MCP_VERSION_2025_11_25
STATELESS = version.MCP_STATELESS_VERSION
PROTOCOL = version.META_PROTOCOL_VERSION
CAPABILITIES = version.META_CLIENT_CAPABILITIES


class TestMcpStateless(MCPHttpCase):
    """Cover the stateless 2026-07-28 revision of the MCP endpoint."""

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_results_carry_the_stateless_envelope(self):
        attachment = self.env['ir.attachment'].create(
            {
                'name': 'notes.txt',
                'raw': BinaryBytes(b'hi'),
                'res_model': 'res.partner',
                'res_id': self.mcp_user.partner_id.id,
            },
        )
        for method, params, scope in (
            ('tools/list', None, 'private'),
            ('prompts/list', None, 'private'),
            ('resources/list', None, 'private'),
            ('resources/templates/list', None, 'public'),
            ('server/discover', None, 'public'),
            (
                'resources/read',
                {'uri': f'odoo://attachment/{attachment.id}'},
                'private',
            ),
            ('tools/call', {'name': 'list_models', 'arguments': {}}, None),
        ):
            with self.subTest(method):
                response = self.mcp_stateless_post(method, params)
                self.assertEqual(response.status_code, 200)
                result = response.json()['result']
                self.assertEqual(result['resultType'], 'complete')
                self.assertEqual(
                    result['_meta'][version.META_SERVER_INFO]['name'],
                    'odoo-mcp-server',
                )
                self.assertEqual(result.get('cacheScope'), scope)
                self.assertEqual('ttlMs' in result, scope is not None)

    def test_discover_advertises_only_the_stateless_revision(self):
        response = self.mcp_stateless_post(
            'server/discover', meta={PROTOCOL: STATELESS}
        )
        self.assertEqual(response.status_code, 200)
        result = response.json()['result']
        self.assertEqual(result['supportedVersions'], [STATELESS])
        self.assertNotIn('serverInfo', result)
        self.assertFalse(result['capabilities']['tools']['listChanged'])

    def test_rejected_requests(self):
        name = version.MCP_NAME_HEADER
        call = ('tools/call', {'name': 'list_models', 'arguments': {}})
        for label, (method, params), meta, headers, status, code in (
            (
                'version header missing',
                ('tools/list', None),
                None,
                {version.MCP_PROTOCOL_VERSION_HEADER: None},
                400,
                -32020,
            ),
            (
                'version header contradicts the meta',
                ('tools/list', None),
                None,
                {version.MCP_PROTOCOL_VERSION_HEADER: HANDSHAKE},
                400,
                -32020,
            ),
            (
                'unsupported version',
                ('tools/list', None),
                {PROTOCOL: '1999-01-01', CAPABILITIES: {}},
                {version.MCP_PROTOCOL_VERSION_HEADER: '1999-01-01'},
                400,
                -32022,
            ),
            (
                'client capabilities missing',
                ('tools/list', None),
                {PROTOCOL: STATELESS},
                None,
                400,
                -32602,
            ),
            (
                'method header missing',
                ('tools/list', None),
                None,
                {version.MCP_METHOD_HEADER: None},
                400,
                -32020,
            ),
            (
                'method header contradicts the body',
                ('tools/list', None),
                None,
                {version.MCP_METHOD_HEADER: 'prompts/list'},
                400,
                -32020,
            ),
            ('name header missing', call, None, {name: None}, 400, -32020),
            ('name header contradicts', call, None, {name: 'other'}, 400, -32020),
            (
                'name header undecodable',
                call,
                None,
                {name: '=?base64?!?='},
                400,
                -32020,
            ),
            ('unknown method', ('nope/nope', None), None, None, 404, -32601),
            ('initialize is retired', ('initialize', None), None, None, 404, -32601),
            ('ping is retired', ('ping', None), None, None, 404, -32601),
        ):
            with self.subTest(label):
                response = self.mcp_stateless_post(method, params, meta, headers)
                self.assertEqual(response.status_code, status)
                self.assertEqual(response.json()['error']['code'], code)

    def test_base64_name_header_is_decoded(self):
        encoded = base64.b64encode(b'list_models').decode()
        response = self.mcp_stateless_post(
            'tools/call',
            {'name': 'list_models', 'arguments': {}},
            headers={version.MCP_NAME_HEADER: f'=?base64?{encoded}?='},
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('isError', response.json()['result'])


class TestClientCapabilities(TransactionCase):
    """Cover the extension negotiation hooks dependent addons build on."""

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_extension_negotiation(self):
        controller = MCPController()
        for params, protocol_version, offered, settings in (
            (
                {'capabilities': {'extensions': {'x': {'a': 1}}}},
                HANDSHAKE,
                True,
                {'a': 1},
            ),
            ({'capabilities': {'extensions': {'x': 'bad'}}}, HANDSHAKE, True, None),
            ({'capabilities': {'extensions': {}}}, HANDSHAKE, False, None),
            ({}, HANDSHAKE, True, None),
            ({}, STATELESS, False, None),
            ({'_meta': {CAPABILITIES: {'extensions': {'x': {}}}}}, STATELESS, True, {}),
        ):
            with self.subTest(params=params, protocol_version=protocol_version):
                self.assertEqual(
                    controller._client_offers_extension(params, 'x', protocol_version),
                    offered,
                )
                self.assertEqual(
                    controller._get_client_extension(params, 'x'), settings
                )
