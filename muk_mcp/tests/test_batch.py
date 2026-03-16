import json

from odoo.tests import common

from odoo.addons.muk_mcp.tools import protocol


class TestBatch(common.TransactionCase):

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_parse_batch_request(self):
        items = [
            {'jsonrpc': '2.0', 'id': 1, 'method': 'ping', 'params': {}},
            {'jsonrpc': '2.0', 'id': 2, 'method': 'ping', 'params': {}},
        ]
        for item in items:
            data, error = protocol.parse_jsonrpc_request(item)
            self.assertIsNone(error)
            self.assertEqual(data['method'], 'ping')

    def test_parse_batch_with_invalid_item(self):
        items = [
            {'jsonrpc': '2.0', 'id': 1, 'method': 'ping', 'params': {}},
            {'id': 2, 'method': 'ping'},
        ]
        data1, error1 = protocol.parse_jsonrpc_request(items[0])
        self.assertIsNone(error1)
        data2, error2 = protocol.parse_jsonrpc_request(items[1])
        self.assertIsNotNone(error2)

    def test_parse_empty_batch(self):
        items = []
        self.assertEqual(len(items), 0)
