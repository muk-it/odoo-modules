from odoo.exceptions import UserError
from odoo.tests import common

from odoo.addons.muk_mcp.tools import parser


class TestParser(common.TransactionCase):
    """Cover id normalization and the JSON/Python literal parsing fallback."""

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_normalize_ids_none_is_empty(self):
        self.assertEqual(parser.normalize_ids(None), [])

    def test_normalize_ids_scalar_int(self):
        self.assertEqual(parser.normalize_ids(42), [42])

    def test_normalize_ids_numeric_string_is_one_id(self):
        self.assertEqual(parser.normalize_ids('42'), [42])
        self.assertEqual(parser.normalize_ids(' 42 '), [42])
        self.assertEqual(parser.normalize_ids('-1'), [-1])

    def test_normalize_ids_non_numeric_string_raises(self):
        for value in ('abc', '', '[1, 2]', '1,2'):
            with self.assertRaises(UserError):
                parser.normalize_ids(value)

    def test_normalize_ids_iterables(self):
        self.assertEqual(parser.normalize_ids([1, 2]), [1, 2])
        self.assertEqual(parser.normalize_ids((3, 4)), [3, 4])
        self.assertEqual(parser.normalize_ids([]), [])

    def test_parse_literal_prefers_json(self):
        self.assertEqual(parser.parse_literal('{"a": 1}'), {'a': 1})
        self.assertEqual(parser.parse_literal('[1, true, null]'), [1, True, None])

    def test_parse_literal_falls_back_to_python(self):
        self.assertEqual(parser.parse_literal("{'a': 1}"), {'a': 1})
        self.assertEqual(parser.parse_literal("[('id', '=', 1)]"), [('id', '=', 1)])

    def test_parse_literal_substitutes_json_keywords(self):
        self.assertEqual(
            parser.parse_literal("{'a': true, 'b': false, 'c': null}"),
            {'a': True, 'b': False, 'c': None},
        )

    def test_parse_literal_corrupts_strings_containing_keywords(self):
        self.assertEqual(
            parser.parse_literal("['contains null here']"),
            ['contains None here'],
        )

    def test_parse_literal_respects_word_boundaries(self):
        self.assertEqual(parser.parse_literal("['nullable']"), ['nullable'])
        self.assertEqual(parser.parse_literal("['trueish']"), ['trueish'])

    def test_parse_literal_rejects_garbage(self):
        with self.assertRaises(ValueError):
            parser.parse_literal('not json and not python')

    def test_parse_literal_rejects_unterminated_input(self):
        with self.assertRaises(SyntaxError):
            parser.parse_literal("['unterminated'")
