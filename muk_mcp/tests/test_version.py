from __future__ import annotations

import dataclasses

from odoo.tests import common, tagged

from odoo.addons.muk_mcp.tests.common import MCPHttpCase
from odoo.addons.muk_mcp.tools import common as mcp_common
from odoo.addons.muk_mcp.tools import protocol, version

RETIRED_VERSION = '2025-03-26'


class TestProtocolVersionTable(common.TransactionCase):
    """Verify the supported-revision table and its lookup helpers."""

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_supported_versions_are_ordered_newest_first(self):
        self.assertEqual(
            version.MCP_SUPPORTED_VERSIONS,
            (
                version.MCP_VERSION_2026_07_28,
                version.MCP_VERSION_2025_11_25,
                version.MCP_VERSION_2025_06_18,
            ),
        )

    def test_the_default_is_the_oldest_served_revision(self):
        self.assertEqual(
            version.MCP_DEFAULT_VERSION,
            version.MCP_SUPPORTED_VERSIONS[-1],
        )

    def test_every_supported_version_has_a_profile(self):
        for candidate in version.MCP_SUPPORTED_VERSIONS:
            self.assertEqual(version.get_profile(candidate).version, candidate)

    def test_the_retired_revision_is_no_longer_served(self):
        self.assertFalse(version.is_supported(RETIRED_VERSION))
        self.assertNotIn(RETIRED_VERSION, version.MCP_SUPPORTED_VERSIONS)

    def test_only_the_newest_revision_is_stateless(self):
        self.assertTrue(
            version.get_profile(version.MCP_VERSION_2026_07_28).stateless,
        )
        self.assertFalse(
            version.get_profile(version.MCP_VERSION_2025_11_25).stateless,
        )
        self.assertFalse(
            version.get_profile(version.MCP_VERSION_2025_06_18).stateless,
        )

    def test_is_supported_rejects_unknown_and_empty_values(self):
        for candidate in (None, '', 'nonsense', '1999-01-01'):
            self.assertFalse(version.is_supported(candidate))

    def test_the_handshake_set_is_the_stateful_revisions(self):
        self.assertEqual(
            version.MCP_HANDSHAKE_VERSIONS,
            (version.MCP_VERSION_2025_11_25, version.MCP_VERSION_2025_06_18),
        )
        self.assertEqual(
            version.MCP_LATEST_HANDSHAKE_VERSION,
            version.MCP_VERSION_2025_11_25,
        )

    def test_negotiate_handshake_echoes_a_stateful_request(self):
        for candidate in version.MCP_HANDSHAKE_VERSIONS:
            self.assertEqual(version.negotiate_handshake(candidate), candidate)

    def test_negotiate_handshake_never_returns_a_stateless_revision(self):
        self.assertEqual(
            version.negotiate_handshake(version.MCP_VERSION_2026_07_28),
            version.MCP_LATEST_HANDSHAKE_VERSION,
        )

    def test_negotiate_handshake_offers_the_latest_for_anything_else(self):
        for candidate in (None, '', 'nonsense', RETIRED_VERSION):
            self.assertEqual(
                version.negotiate_handshake(candidate),
                version.MCP_LATEST_HANDSHAKE_VERSION,
            )

    def test_get_profile_falls_back_to_the_default(self):
        self.assertEqual(
            version.get_profile('nonsense').version,
            version.MCP_DEFAULT_VERSION,
        )
        self.assertEqual(
            version.get_profile(None).version,
            version.MCP_DEFAULT_VERSION,
        )

    def test_profiles_are_immutable(self):
        profile = version.get_profile(version.MCP_DEFAULT_VERSION)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            profile.stateless = True

    def test_meta_keys_use_the_reserved_namespace(self):
        for key in (
            version.META_PROTOCOL_VERSION,
            version.META_CLIENT_INFO,
            version.META_CLIENT_CAPABILITIES,
        ):
            self.assertTrue(key.startswith('io.modelcontextprotocol/'))


class TestProtocolResultBuilders(common.TransactionCase):
    """Verify the initialize, discover and version-error payload builders."""

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_initialize_result_carries_the_negotiated_version(self):
        for candidate in version.MCP_SUPPORTED_VERSIONS:
            result = protocol.make_initialize_result(candidate)
            self.assertEqual(result['protocolVersion'], candidate)

    def test_initialize_result_merges_extra_capabilities(self):
        result = protocol.make_initialize_result(
            version.MCP_DEFAULT_VERSION,
            capabilities={'extensions': {'x': {}}},
        )
        self.assertEqual(result['capabilities']['extensions'], {'x': {}})
        self.assertTrue(result['capabilities']['tools']['listChanged'])

    def test_discover_result_lists_every_served_version(self):
        result = protocol.make_discover_result()
        self.assertEqual(
            result['supportedVersions'],
            list(version.MCP_SUPPORTED_VERSIONS),
        )

    def test_discover_result_has_no_single_negotiated_version(self):
        self.assertNotIn('protocolVersion', protocol.make_discover_result())

    def test_discover_and_initialize_agree_on_the_server_identity(self):
        discover = protocol.make_discover_result()
        initialize = protocol.make_initialize_result(
            version.MCP_DEFAULT_VERSION
        )
        self.assertEqual(discover['serverInfo'], initialize['serverInfo'])

    def test_unsupported_version_error_reports_what_is_served(self):
        error = protocol.make_unsupported_version_error(
            '1999-01-01', request_id=7
        )
        self.assertEqual(error['id'], 7)
        self.assertEqual(
            error['error']['code'],
            mcp_common.MCP_UNSUPPORTED_PROTOCOL_VERSION,
        )
        self.assertEqual(error['error']['data']['requested'], '1999-01-01')
        self.assertEqual(
            error['error']['data']['supported'],
            list(version.MCP_SUPPORTED_VERSIONS),
        )


@tagged('post_install', '-at_install')
class TestVersionNegotiationHttp(MCPHttpCase):
    """Cover revision negotiation over the HTTP transport."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.session_model = cls.env['muk_mcp.session']

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _initialize(self, protocol_version: str | None = None) -> dict:
        """Run ``initialize`` and return the parsed HTTP response and body."""
        params = (
            {'protocolVersion': protocol_version} if protocol_version else {}
        )
        response = self.mcp_post({
            'jsonrpc': '2.0',
            'id': 1,
            'method': 'initialize',
            'params': params,
        })
        return {
            'response': response,
            'body': response.json(),
            'session_id': response.headers.get('Mcp-Session-Id'),
        }

    def _stored_version(self, session_id: str) -> str:
        """Return the protocol version recorded on the named session."""
        session = self.session_model.search([('session_id', '=', session_id)])
        return session.protocol_version

    # ----------------------------------------------------------
    # Tests: handshake negotiation
    # ----------------------------------------------------------

    def test_initialize_echoes_each_stateful_revision(self):
        for candidate in (
            version.MCP_VERSION_2025_06_18,
            version.MCP_VERSION_2025_11_25,
        ):
            outcome = self._initialize(candidate)
            self.assertEqual(
                outcome['body']['result']['protocolVersion'], candidate
            )

    def test_initialize_downgrades_an_unknown_revision(self):
        outcome = self._initialize('1999-01-01')
        self.assertEqual(
            outcome['body']['result']['protocolVersion'],
            version.MCP_LATEST_HANDSHAKE_VERSION,
        )
        self.assertNotIn('error', outcome['body'])

    def test_initialize_downgrades_the_retired_revision(self):
        outcome = self._initialize(RETIRED_VERSION)
        self.assertEqual(
            outcome['body']['result']['protocolVersion'],
            version.MCP_LATEST_HANDSHAKE_VERSION,
        )

    def test_initialize_without_a_requested_revision_offers_the_latest(self):
        outcome = self._initialize()
        self.assertEqual(
            outcome['body']['result']['protocolVersion'],
            version.MCP_LATEST_HANDSHAKE_VERSION,
        )

    def test_initialize_refuses_to_hand_out_the_stateless_revision(self):
        outcome = self._initialize(version.MCP_VERSION_2026_07_28)
        negotiated = outcome['body']['result']['protocolVersion']
        self.assertEqual(negotiated, version.MCP_LATEST_HANDSHAKE_VERSION)
        self.assertFalse(version.get_profile(negotiated).stateless)
        self.assertEqual(
            self._stored_version(outcome['session_id']),
            version.MCP_LATEST_HANDSHAKE_VERSION,
        )

    def test_a_session_negotiated_that_way_keeps_working(self):
        outcome = self._initialize(version.MCP_VERSION_2026_07_28)
        session_id = outcome['session_id']
        self.mcp_post(
            {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
            session_id=session_id,
        )
        response = self.mcp_post(self.mcp_ping(), session_id=session_id)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['result'], {})

    def test_the_negotiated_revision_is_stored_on_the_session(self):
        outcome = self._initialize(version.MCP_VERSION_2025_11_25)
        self.assertEqual(
            self._stored_version(outcome['session_id']),
            version.MCP_VERSION_2025_11_25,
        )

    def test_the_stored_revision_is_the_negotiated_not_the_requested_one(self):
        outcome = self._initialize('1999-01-01')
        self.assertEqual(
            self._stored_version(outcome['session_id']),
            version.MCP_LATEST_HANDSHAKE_VERSION,
        )

    def test_initialize_is_gone_from_the_stateless_revision(self):
        response = self.mcp_stateless_post('initialize', {})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.json()['error']['code'],
            mcp_common.JSONRPC_METHOD_NOT_FOUND,
        )

    # ----------------------------------------------------------
    # Tests: the version header
    # ----------------------------------------------------------

    def test_an_unsupported_header_revision_is_rejected(self):
        session_id = self.mcp_handshake()
        response = self.mcp_post(
            self.mcp_ping(),
            session_id=session_id,
            protocol_version='1999-01-01',
        )
        self.assertEqual(response.status_code, 400)
        error = response.json()['error']
        self.assertEqual(
            error['code'], mcp_common.MCP_UNSUPPORTED_PROTOCOL_VERSION
        )
        self.assertEqual(error['data']['requested'], '1999-01-01')
        self.assertEqual(
            error['data']['supported'],
            list(version.MCP_SUPPORTED_VERSIONS),
        )

    def test_the_retired_revision_is_rejected_in_the_header(self):
        session_id = self.mcp_handshake()
        response = self.mcp_post(
            self.mcp_ping(),
            session_id=session_id,
            protocol_version=RETIRED_VERSION,
        )
        self.assertEqual(response.status_code, 400)

    def test_a_supported_header_revision_is_accepted(self):
        session_id = self.mcp_handshake(
            protocol_version=version.MCP_VERSION_2025_11_25,
        )
        response = self.mcp_post(
            self.mcp_ping(),
            session_id=session_id,
            protocol_version=version.MCP_VERSION_2025_11_25,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['result'], {})

    def test_a_header_contradicting_the_meta_is_rejected(self):
        response = self.mcp_stateless_post(
            'tools/list',
            protocol_version=version.MCP_VERSION_2026_07_28,
            headers={
                version.MCP_PROTOCOL_VERSION_HEADER:
                    version.MCP_VERSION_2025_11_25,
            },
        )
        self.assertEqual(response.status_code, 400)
        error = response.json()['error']
        self.assertEqual(error['code'], mcp_common.JSONRPC_INVALID_PARAMS)
        self.assertIn('mismatch', error['message'])

    def test_a_terminated_session_is_answered_404(self):
        session_id = self.mcp_handshake()
        self.mcp_delete(session_id=session_id)
        response = self.mcp_post(
            {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list', 'params': {}},
            session_id=session_id,
        )
        self.assertEqual(response.status_code, 404)

    def test_an_unknown_session_is_answered_404(self):
        response = self.mcp_post(
            {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list', 'params': {}},
            session_id='no-such-session',
        )
        self.assertEqual(response.status_code, 404)

    def test_a_request_without_any_session_header_is_not_404(self):
        response = self.mcp_post(
            {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list', 'params': {}},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()['error']['code'],
            mcp_common.JSONRPC_INVALID_REQUEST,
        )

    def test_the_stateless_revision_requires_the_version_header(self):
        response = self.mcp_stateless_post('tools/list', send_header=False)
        self.assertEqual(response.status_code, 400)
        error = response.json()['error']
        self.assertEqual(error['code'], mcp_common.JSONRPC_INVALID_PARAMS)
        self.assertIn(version.MCP_PROTOCOL_VERSION_HEADER, error['message'])

    def test_a_headerless_request_falls_back_to_the_session_revision(self):
        session_id = self.mcp_handshake(
            protocol_version=version.MCP_VERSION_2025_11_25,
        )
        response = self.mcp_post(self.mcp_ping(), session_id=session_id)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['result'], {})

    # ----------------------------------------------------------
    # Tests: the stateless revision
    # ----------------------------------------------------------

    def test_tools_list_needs_no_session(self):
        response = self.mcp_stateless_post('tools/list')
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.json()['result']['tools'], list)

    def test_a_stateless_exchange_creates_no_session(self):
        before = self.session_model.search_count([])
        self.mcp_stateless_post('tools/list')
        self.mcp_stateless_post('prompts/list')
        self.assertEqual(self.session_model.search_count([]), before)

    def test_a_stateless_tool_call_returns_its_result(self):
        response = self.mcp_stateless_post(
            'tools/call',
            {'name': 'list_models', 'arguments': {}},
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('error', response.json())

    def test_discover_advertises_every_served_revision(self):
        response = self.mcp_stateless_post('server/discover')
        self.assertEqual(response.status_code, 200)
        result = response.json()['result']
        self.assertEqual(
            result['supportedVersions'],
            list(version.MCP_SUPPORTED_VERSIONS),
        )
        self.assertIn('serverInfo', result)

    def test_discover_needs_only_the_protocol_version_in_meta(self):
        response = self.mcp_stateless_post(
            'server/discover',
            meta=self.mcp_meta(full=False),
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('supportedVersions', response.json()['result'])

    def test_discover_is_absent_from_the_stateful_revisions(self):
        session_id = self.mcp_handshake()
        body = self.mcp_json(
            {
                'jsonrpc': '2.0',
                'id': 1,
                'method': 'server/discover',
                'params': {},
            },
            session_id=session_id,
        )
        self.assertEqual(
            body['error']['code'],
            mcp_common.JSONRPC_METHOD_NOT_FOUND,
        )

    def test_the_stateless_revision_withdraws_list_changed(self):
        response = self.mcp_stateless_post('server/discover')
        capabilities = response.json()['result']['capabilities']
        self.assertFalse(capabilities['tools']['listChanged'])
        self.assertFalse(capabilities['resources']['listChanged'])

    def test_the_stateful_revisions_keep_the_list_changed_capability(self):
        outcome = self._initialize()
        capabilities = outcome['body']['result']['capabilities']
        self.assertTrue(capabilities['tools']['listChanged'])

    # ----------------------------------------------------------
    # Tests: required stateless metadata
    # ----------------------------------------------------------

    def test_a_stateless_request_without_client_info_is_rejected(self):
        meta = self.mcp_meta()
        del meta[version.META_CLIENT_INFO]
        response = self.mcp_stateless_post('tools/list', meta=meta)
        self.assertEqual(response.status_code, 400)
        error = response.json()['error']
        self.assertEqual(error['code'], mcp_common.JSONRPC_INVALID_PARAMS)
        self.assertIn(version.META_CLIENT_INFO, error['message'])

    def test_a_stateless_request_without_client_capabilities_is_rejected(self):
        meta = self.mcp_meta()
        del meta[version.META_CLIENT_CAPABILITIES]
        response = self.mcp_stateless_post('tools/list', meta=meta)
        self.assertEqual(response.status_code, 400)
        self.assertIn(
            version.META_CLIENT_CAPABILITIES,
            response.json()['error']['message'],
        )

    def test_empty_client_capabilities_are_accepted(self):
        response = self.mcp_stateless_post(
            'tools/list',
            meta=self.mcp_meta(capabilities={}),
        )
        self.assertEqual(response.status_code, 200)

    def test_the_stateful_revisions_require_no_meta(self):
        session_id = self.mcp_handshake()
        response = self.mcp_post(
            {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list', 'params': {}},
            session_id=session_id,
        )
        self.assertEqual(response.status_code, 200)

    # ----------------------------------------------------------
    # Tests: methods retired by the stateless revision
    # ----------------------------------------------------------

    def test_the_retired_methods_are_gone_from_the_stateless_revision(self):
        for method in (
            'ping',
            'logging/setLevel',
            'notifications/initialized',
            'notifications/roots/list_changed',
        ):
            response = self.mcp_stateless_post(method, {})
            self.assertEqual(
                response.status_code,
                404,
                f'{method} should be unroutable on the stateless revision',
            )

    def test_the_retired_methods_still_serve_the_stateful_revisions(self):
        session_id = self.mcp_handshake()
        for method in ('ping', 'logging/setLevel'):
            body = self.mcp_json(
                {'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': {}},
                session_id=session_id,
            )
            self.assertNotIn('error', body, f'{method} should still be served')

    def test_an_unknown_method_is_a_plain_200_on_the_stateful_revisions(self):
        session_id = self.mcp_handshake()
        response = self.mcp_post(
            {'jsonrpc': '2.0', 'id': 1, 'method': 'nope/nope', 'params': {}},
            session_id=session_id,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()['error']['code'],
            mcp_common.JSONRPC_METHOD_NOT_FOUND,
        )

    # ----------------------------------------------------------
    # Tests: the retired GET and DELETE routes
    # ----------------------------------------------------------

    def test_the_get_stream_is_gone_from_the_stateless_revision(self):
        response = self.mcp_get(
            protocol_version=version.MCP_VERSION_2026_07_28,
            headers={'Accept': 'text/event-stream'},
        )
        self.assertEqual(response.status_code, 405)

    def test_the_get_stream_still_serves_the_stateful_revisions(self):
        session_id = self.mcp_handshake()
        response = self.mcp_get(
            session_id=session_id,
            headers={'Accept': 'text/event-stream'},
        )
        self.assertEqual(response.status_code, 200)

    def test_delete_is_gone_from_the_stateless_revision(self):
        response = self.mcp_delete(
            protocol_version=version.MCP_VERSION_2026_07_28,
        )
        self.assertEqual(response.status_code, 405)

    def test_delete_still_terminates_a_session(self):
        session_id = self.mcp_handshake()
        self.assertEqual(
            self.mcp_delete(session_id=session_id).status_code, 200
        )
        session = self.session_model.search([('session_id', '=', session_id)])
        self.assertFalse(session.active)

    # ----------------------------------------------------------
    # Tests: the two eras side by side
    # ----------------------------------------------------------

    def test_both_eras_are_served_by_the_same_endpoint(self):
        session_id = self.mcp_handshake(
            protocol_version=version.MCP_VERSION_2025_11_25,
        )
        stateful = self.mcp_post(
            {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list', 'params': {}},
            session_id=session_id,
        )
        stateless = self.mcp_stateless_post('tools/list', request_id=2)
        self.assertEqual(stateful.status_code, 200)
        self.assertEqual(stateless.status_code, 200)
        self.assertEqual(
            stateful.json()['result']['tools'],
            stateless.json()['result']['tools'],
        )

    def test_a_stateless_request_ignores_a_stale_session_header(self):
        session_id = self.mcp_handshake()
        self.mcp_delete(session_id=session_id)
        response = self.mcp_stateless_post('tools/list', session_id=session_id)
        self.assertEqual(response.status_code, 200)


@tagged('post_install', '-at_install')
class TestOriginValidation(MCPHttpCase):
    """Cover the ``Origin`` check guarding against DNS rebinding."""

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _ping_from(self, origin: str | None) -> int:
        """Ping the endpoint from ``origin`` and return the HTTP status."""
        self.env['ir.config_parameter'].sudo().set_param(
            'web.base.url',
            self.base_url(),
        )
        session_id = self.mcp_handshake()
        headers = {'Origin': origin} if origin else {}
        return self.mcp_post(
            self.mcp_ping(),
            session_id=session_id,
            headers=headers,
        ).status_code

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_a_request_without_an_origin_is_served(self):
        self.assertEqual(self._ping_from(None), 200)

    def test_a_same_origin_request_is_served(self):
        self.assertEqual(self._ping_from(self.base_url()), 200)

    def test_a_foreign_origin_is_rejected(self):
        self.assertEqual(self._ping_from('https://evil.example'), 403)

    def test_a_configured_origin_is_served(self):
        self.env['ir.config_parameter'].sudo().set_param(
            'muk_mcp.allowed_origins',
            'https://partner.example, https://other.example',
        )
        self.assertEqual(self._ping_from('https://partner.example'), 200)
        self.assertEqual(self._ping_from('https://other.example'), 200)
        self.assertEqual(self._ping_from('https://evil.example'), 403)

    def test_the_escape_hatch_serves_any_origin(self):
        self.env['ir.config_parameter'].sudo().set_param(
            'muk_mcp.allow_any_origin',
            'True',
        )
        self.assertEqual(self._ping_from('https://evil.example'), 200)

    def test_a_rejected_origin_is_audited(self):
        log_model = self.env['muk_mcp.log']
        before = log_model.search_count([('method', '=', 'origin_rejected')])
        self._ping_from('https://evil.example')
        self.assertEqual(
            log_model.search_count([('method', '=', 'origin_rejected')]),
            before + 1,
        )

    def test_the_allow_list_ignores_the_request_host(self):
        self.env['ir.config_parameter'].sudo().set_param(
            'web.base.url', 'https://real.example',
        )
        session_id = self.mcp_handshake()
        response = self.mcp_post(
            self.mcp_ping(),
            session_id=session_id,
            headers={
                'Origin': self.base_url(),
                'Host': self.base_url().split('//')[1],
            },
        )
        self.assertEqual(response.status_code, 403)

    def test_the_get_route_checks_the_origin(self):
        session_id = self.mcp_handshake()
        response = self.mcp_get(
            session_id=session_id,
            headers={
                'Accept': 'text/event-stream',
                'Origin': 'https://evil.example',
            },
        )
        self.assertEqual(response.status_code, 403)

    def test_the_delete_route_checks_the_origin(self):
        session_id = self.mcp_handshake()
        response = self.mcp_delete(
            session_id=session_id,
            headers={'Origin': 'https://evil.example'},
        )
        self.assertEqual(response.status_code, 403)
        session = self.env['muk_mcp.session'].search(
            [('session_id', '=', session_id)],
        )
        self.assertTrue(session.active)
