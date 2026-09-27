import json

from odoo.tests import TransactionCase

from odoo.addons.muk_web_utils.tools.encoder import (
    LogEncoder,
    RecordEncoder,
    ResponseEncoder,
    limit_text_size,
    ustr_sql,
)


class TestEncoder(TransactionCase):
    """Test the JSON encoders and text helpers from ``tools.encoder``."""

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_log_encoder_round_trips_every_indent(self):
        data = {'a': [1, 2, {'b': 'c'}], 'd': None, 'e': True, 'pi': 3.14}
        for indent, multiline in ((None, False), (4, True), ('  ', True)):
            with self.subTest(indent=indent):
                result = json.dumps(data, cls=LogEncoder, indent=indent)
                self.assertEqual('\n' in result, multiline)
                self.assertEqual(json.loads(result), data)

    def test_log_encoder_truncates_long_strings(self):
        self.assertEqual(
            json.dumps({'key': 'x' * 500, 'short': 'y'}, cls=LogEncoder),
            '{"key": "' + 'x' * 149 + '..., "short": "y"}',
        )

    def test_limit_text_size(self):
        self.assertEqual(limit_text_size('hello'), 'hello')
        self.assertEqual(limit_text_size('x' * 30000), 'x' * 25000 + '\n\n...')

    def test_record_encoder_renders_records_and_delegates_the_rest(self):
        partners = self.env['res.partner'].create([{'name': 'A'}, {'name': 'B'}])
        result = json.loads(json.dumps({'p': partners, 'b': b'hi'}, cls=RecordEncoder))
        self.assertEqual(
            result, {'p': [[partners[0].id, 'A'], [partners[1].id, 'B']], 'b': 'hi'}
        )

    def test_response_encoder_uses_the_web_client_serializer(self):
        self.assertEqual(json.dumps({'b': b'hi'}, cls=ResponseEncoder), '{"b": "hi"}')

    def test_ustr_sql_replaces_nul_and_invalid_bytes(self):
        self.assertEqual(ustr_sql(b'a\x00b\xffc'), 'a�b�c')
