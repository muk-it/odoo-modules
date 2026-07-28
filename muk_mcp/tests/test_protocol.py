import json

from odoo.tests import common

from odoo.addons.muk_mcp.tools import protocol, version, common as mcp_common


class TestProtocol(common.TransactionCase):

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_make_jsonrpc_response(self):
        result = protocol.make_jsonrpc_response({'foo': 'bar'}, request_id=1)
        self.assertEqual(result['jsonrpc'], '2.0')
        self.assertEqual(result['id'], 1)
        self.assertEqual(result['result'], {'foo': 'bar'})
        self.assertNotIn('error', result)

    def test_make_jsonrpc_error(self):
        result = protocol.make_jsonrpc_error(
            mcp_common.JSONRPC_METHOD_NOT_FOUND,
            'Method not found',
            request_id=2,
        )
        self.assertEqual(result['jsonrpc'], '2.0')
        self.assertEqual(result['id'], 2)
        self.assertIn('error', result)
        self.assertEqual(result['error']['code'], -32601)
        self.assertEqual(result['error']['message'], 'Method not found')

    def test_parse_jsonrpc_request_valid(self):
        raw = json.dumps({
            'jsonrpc': '2.0',
            'id': 1,
            'method': 'initialize',
            'params': {},
        })
        data, error = protocol.parse_jsonrpc_request(raw)
        self.assertIsNone(error)
        self.assertIsNotNone(data)
        self.assertEqual(data['method'], 'initialize')

    def test_parse_jsonrpc_request_invalid_json(self):
        data, error = protocol.parse_jsonrpc_request('{invalid}')
        self.assertIsNone(data)
        self.assertIsNotNone(error)
        self.assertEqual(
            error['error']['code'], mcp_common.JSONRPC_PARSE_ERROR
        )

    def test_parse_jsonrpc_request_missing_version(self):
        raw = json.dumps({'id': 1, 'method': 'ping'})
        data, error = protocol.parse_jsonrpc_request(raw)
        self.assertIsNone(data)
        self.assertIsNotNone(error)
        self.assertEqual(
            error['error']['code'], mcp_common.JSONRPC_INVALID_REQUEST
        )

    def test_parse_jsonrpc_request_missing_method(self):
        raw = json.dumps({'jsonrpc': '2.0', 'id': 1})
        data, error = protocol.parse_jsonrpc_request(raw)
        self.assertIsNone(data)
        self.assertIsNotNone(error)

    def test_parse_jsonrpc_request_rejects_array_params(self):
        raw = json.dumps({
            'jsonrpc': '2.0',
            'id': 4,
            'method': 'tools/list',
            'params': [1],
        })
        data, error = protocol.parse_jsonrpc_request(raw)
        self.assertIsNone(data)
        self.assertEqual(
            error['error']['code'], mcp_common.JSONRPC_INVALID_REQUEST
        )
        self.assertEqual(error['id'], 4)

    def test_parse_jsonrpc_request_rejects_scalar_params(self):
        for value in ('x', 5, True):
            raw = json.dumps({
                'jsonrpc': '2.0',
                'id': 5,
                'method': 'ping',
                'params': value,
            })
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

    def test_make_initialize_result(self):
        result = protocol.make_initialize_result(
            version.MCP_DEFAULT_VERSION
        )
        self.assertEqual(
            result['protocolVersion'], version.MCP_DEFAULT_VERSION
        )
        self.assertIn('tools', result['capabilities'])
        self.assertTrue(result['capabilities']['tools']['listChanged'])
        self.assertEqual(
            result['serverInfo']['name'], mcp_common.MCP_SERVER_NAME
        )

    def test_make_tool_result(self):
        content = [protocol.make_text_content('hello')]
        result = protocol.make_tool_result(content)
        self.assertEqual(len(result['content']), 1)
        self.assertEqual(result['content'][0]['type'], 'text')
        self.assertEqual(result['content'][0]['text'], 'hello')
        self.assertNotIn('isError', result)

    def test_make_tool_result_error(self):
        content = [protocol.make_text_content('failed')]
        result = protocol.make_tool_result(content, is_error=True)
        self.assertTrue(result['isError'])

    def test_make_text_content(self):
        content = protocol.make_text_content('hello world')
        self.assertEqual(content['type'], 'text')
        self.assertEqual(content['text'], 'hello world')
