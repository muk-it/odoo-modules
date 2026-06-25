import json
from datetime import date, datetime

from odoo.tests import common, tagged

from odoo.addons.muk_web_utils.tools.encoder import (
    LogEncoder,
    RecordEncoder,
    RequestEncoder,
    ResponseEncoder,
    limit_text_size,
    ustr_sql,
)


@tagged('post_install', '-at_install')
class TestEncoder(common.TransactionCase):
    """Test the JSON encoders and text helpers from ``tools.encoder``."""

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_accepts_int_indent(self):
        data = {'key': 'value', 'nested': {'inner': 1}}
        result = json.dumps(data, cls=LogEncoder, indent=4)
        self.assertIn('\n', result)
        self.assertEqual(json.loads(result), data)

    def test_accepts_str_indent(self):
        data = {'a': 1}
        result = json.dumps(data, cls=LogEncoder, indent='  ')
        self.assertIn('\n', result)
        self.assertEqual(json.loads(result), data)

    def test_none_indent_compact(self):
        data = {'a': 1}
        result = json.dumps(data, cls=LogEncoder, indent=None)
        self.assertNotIn('\n', result)
        self.assertEqual(json.loads(result), data)

    def test_encodes_floats_as_numbers(self):
        data = {'pi': 3.14}
        result = json.dumps(data, cls=LogEncoder, indent=2)
        parsed = json.loads(result)
        self.assertIsInstance(parsed['pi'], float)
        self.assertAlmostEqual(parsed['pi'], 3.14)

    def test_truncates_long_strings(self):
        data = {'key': 'x' * 500}
        result = json.dumps(data, cls=LogEncoder)
        self.assertIn('...', result)

    def test_short_strings_intact(self):
        data = {'key': 'short'}
        result = json.dumps(data, cls=LogEncoder)
        self.assertEqual(json.loads(result)['key'], 'short')

    def test_nested_structures(self):
        data = {'a': [1, 2, {'b': 'c'}], 'd': None, 'e': True}
        result = json.dumps(data, cls=LogEncoder, indent=4)
        self.assertEqual(json.loads(result), data)

    def test_limit_text_size_short(self):
        self.assertEqual(limit_text_size('hello'), 'hello')

    def test_limit_text_size_long(self):
        text = 'x' * 30000
        result = limit_text_size(text)
        self.assertTrue(result.endswith('...'))
        self.assertLess(len(result), len(text))

    def test_request_encoder_datetime(self):
        result = json.dumps({'d': datetime(2026, 4, 16, 12, 0, 0)}, cls=RequestEncoder)
        self.assertIn('2026-04-16', result)

    def test_request_encoder_date(self):
        result = json.dumps({'d': date(2026, 4, 16)}, cls=RequestEncoder)
        self.assertIn('2026-04-16', result)

    def test_request_encoder_bytes(self):
        result = json.dumps({'b': b'hello'}, cls=RequestEncoder)
        self.assertEqual(json.loads(result), {'b': 'hello'})

    def test_request_encoder_record(self):
        partner = self.env['res.partner'].create({'name': 'Cyberlab Enc Test'})
        result = json.loads(json.dumps({'p': partner}, cls=RequestEncoder))
        self.assertEqual(result['p'], [[partner.id, 'Cyberlab Enc Test']])

    def test_response_encoder_bytes(self):
        result = json.dumps({'b': b'hi'}, cls=ResponseEncoder)
        self.assertEqual(json.loads(result), {'b': 'hi'})

    def test_response_encoder_datetime_via_json_default(self):
        result = json.dumps({'d': datetime(2026, 4, 16, 12, 0, 0)}, cls=ResponseEncoder)
        self.assertIn('2026-04-16', result)

    def test_record_encoder_record(self):
        partner = self.env['res.partner'].create({'name': 'Cyberlab Rec Test'})
        result = json.loads(json.dumps({'p': partner}, cls=RecordEncoder))
        self.assertEqual(result['p'], [[partner.id, 'Cyberlab Rec Test']])

    def test_record_encoder_bytes_passthrough(self):
        result = json.dumps({'b': b'bytes'}, cls=RecordEncoder)
        self.assertEqual(json.loads(result), {'b': 'bytes'})

    def test_ustr_sql_removes_null_bytes(self):
        result = ustr_sql(b'hello\x00world')
        self.assertNotIn('\x00', result)
        self.assertIn('\ufffd', result)

    def test_ustr_sql_normal_string(self):
        self.assertEqual(ustr_sql(b'hello world'), 'hello world')
