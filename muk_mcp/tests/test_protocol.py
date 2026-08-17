import json

from odoo.tests import common

from odoo.addons.muk_mcp.tools import common as mcp_common
from odoo.addons.muk_mcp.tools import protocol, version


class TestProtocol(common.TransactionCase):
    """Verify JSON-RPC parsing and MCP result/content construction helpers."""

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_parse_jsonrpc_request_valid(self):
        raw = json.dumps(
            {
                'jsonrpc': '2.0',
                'id': 1,
                'method': 'initialize',
                'params': {},
            },
        )
        data, error = protocol.parse_jsonrpc_request(raw)
        self.assertIsNone(error)
        self.assertIsNotNone(data)
        self.assertEqual(data['method'], 'initialize')

    def test_parse_jsonrpc_request_invalid_json(self):
        data, error = protocol.parse_jsonrpc_request('{invalid}')
        self.assertIsNone(data)
        self.assertIsNotNone(error)
        self.assertEqual(
            error['error']['code'],
            mcp_common.JSONRPC_PARSE_ERROR,
        )

    def test_parse_jsonrpc_request_missing_version(self):
        raw = json.dumps({'id': 1, 'method': 'ping'})
        data, error = protocol.parse_jsonrpc_request(raw)
        self.assertIsNone(data)
        self.assertIsNotNone(error)
        self.assertEqual(
            error['error']['code'],
            mcp_common.JSONRPC_INVALID_REQUEST,
        )

    def test_parse_jsonrpc_request_missing_method(self):
        raw = json.dumps({'jsonrpc': '2.0', 'id': 1})
        data, error = protocol.parse_jsonrpc_request(raw)
        self.assertIsNone(data)
        self.assertEqual(
            error['error']['code'],
            mcp_common.JSONRPC_INVALID_REQUEST,
        )
        self.assertEqual(
            error['error']['message'],
            'Invalid Request: method is required',
        )
        self.assertEqual(error['id'], 1)

    def test_parse_jsonrpc_request_non_string_method(self):
        raw = json.dumps({'jsonrpc': '2.0', 'id': 3, 'method': 42})
        data, error = protocol.parse_jsonrpc_request(raw)
        self.assertIsNone(data)
        self.assertEqual(
            error['error']['code'],
            mcp_common.JSONRPC_INVALID_REQUEST,
        )
        self.assertEqual(error['id'], 3)

    def test_parse_jsonrpc_request_rejects_array_params(self):
        raw = json.dumps(
            {'jsonrpc': '2.0', 'id': 4, 'method': 'tools/list', 'params': [1]},
        )
        data, error = protocol.parse_jsonrpc_request(raw)
        self.assertIsNone(data)
        self.assertEqual(
            error['error']['code'],
            mcp_common.JSONRPC_INVALID_REQUEST,
        )
        self.assertEqual(error['id'], 4)

    def test_parse_jsonrpc_request_rejects_scalar_params(self):
        for value in ('x', 5, True):
            raw = json.dumps(
                {'jsonrpc': '2.0', 'id': 5, 'method': 'ping', 'params': value},
            )
            data, error = protocol.parse_jsonrpc_request(raw)
            self.assertIsNone(data, value)
            self.assertEqual(
                error['error']['code'],
                mcp_common.JSONRPC_INVALID_REQUEST,
                value,
            )

    def test_parse_jsonrpc_request_allows_absent_params(self):
        raw = json.dumps({'jsonrpc': '2.0', 'id': 6, 'method': 'ping'})
        data, error = protocol.parse_jsonrpc_request(raw)
        self.assertIsNone(error)
        self.assertEqual(data['method'], 'ping')

    def test_make_result_envelope_names_the_result_type(self):
        envelope = protocol.make_result_envelope(
            {'foo': 'bar'},
            version.get_profile(version.MCP_VERSION_2026_07_28),
            'tools/call',
        )
        self.assertEqual(envelope['resultType'], 'complete')
        self.assertEqual(envelope['foo'], 'bar')

    def test_make_result_envelope_leaves_an_earlier_revision_untouched(self):
        result = {'foo': 'bar'}
        self.assertEqual(
            protocol.make_result_envelope(
                result,
                version.get_profile(version.MCP_VERSION_2025_11_25),
                'tools/list',
            ),
            result,
        )

    def test_make_result_envelope_overrides_a_handler_result_type(self):
        envelope = protocol.make_result_envelope(
            {'resultType': 'input_required'},
            version.get_profile(version.MCP_VERSION_2026_07_28),
            'tools/call',
        )
        self.assertEqual(envelope['resultType'], 'complete')

    def test_make_result_envelope_carries_the_caching_hints(self):
        envelope = protocol.make_result_envelope(
            {'tools': []},
            version.get_profile(version.MCP_VERSION_2026_07_28),
            'tools/list',
        )
        self.assertEqual(envelope['cacheScope'], 'private')
        self.assertGreaterEqual(envelope['ttlMs'], 0)

    def test_make_result_envelope_carries_no_hints_for_an_uncacheable_method(self):
        envelope = protocol.make_result_envelope(
            {'content': []},
            version.get_profile(version.MCP_VERSION_2026_07_28),
            'tools/call',
        )
        self.assertNotIn('ttlMs', envelope)
        self.assertNotIn('cacheScope', envelope)

    def test_make_result_envelope_carries_the_server_identity(self):
        envelope = protocol.make_result_envelope(
            {'tools': []},
            version.get_profile(version.MCP_VERSION_2026_07_28),
            'tools/list',
        )
        self.assertEqual(
            envelope['_meta'][version.META_SERVER_INFO],
            protocol.make_server_info(),
        )

    def test_make_initialize_result(self):
        result = protocol.make_initialize_result(version.MCP_DEFAULT_VERSION)
        self.assertEqual(
            result['protocolVersion'],
            version.MCP_DEFAULT_VERSION,
        )
        self.assertIn('tools', result['capabilities'])
        self.assertTrue(result['capabilities']['tools']['listChanged'])
        self.assertEqual(
            result['serverInfo']['name'],
            mcp_common.MCP_SERVER_NAME,
        )

    def test_make_tool_result_error(self):
        content = [protocol.make_text_content('failed')]
        result = protocol.make_tool_result(content, is_error=True)
        self.assertTrue(result['isError'])

    def test_make_resource_content_with_blob(self):
        content = protocol.make_resource_content(
            'odoo://attachment/1',
            mime_type='application/pdf',
            blob='CCCC',
        )
        self.assertEqual(content['type'], 'resource')
        self.assertEqual(content['resource']['uri'], 'odoo://attachment/1')
        self.assertEqual(
            content['resource']['mimeType'],
            'application/pdf',
        )
        self.assertEqual(content['resource']['blob'], 'CCCC')
        self.assertNotIn('text', content['resource'])

    def test_make_resource_content_with_text(self):
        content = protocol.make_resource_content(
            'odoo://thing/1',
            mime_type='text/plain',
            text='hi',
        )
        self.assertEqual(content['resource']['text'], 'hi')
        self.assertNotIn('blob', content['resource'])
