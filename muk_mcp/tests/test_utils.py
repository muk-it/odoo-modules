import collections
import json
import time

from odoo.exceptions import UserError
from odoo.tests import TransactionCase

from odoo.addons.muk_mcp.tools.parser import coerce_json_value, normalize_ids
from odoo.addons.muk_mcp.tools.rate_limit import RateLimiter
from odoo.addons.muk_mcp.tools.schema import to_strict_schema


class TestMcpUtils(TransactionCase):
    """Cover the argument parsing, schema reduction and rate limiting helpers."""

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_normalize_ids(self):
        for value, expected in (
            (None, []),
            (42, [42]),
            (' -1 ', [-1]),
            ([1, 2], [1, 2]),
            ((3, 4), [3, 4]),
        ):
            with self.subTest(value):
                self.assertEqual(normalize_ids(value), expected)
        for value in ('abc', '', '1,2'):
            with self.subTest(value), self.assertRaises(UserError):
                normalize_ids(value)

    def test_coerce_json_value(self):
        for value, expected in (
            (json.dumps(json.dumps(json.dumps([1]))), [1]),
            (
                "{'a': true, 'b': null, 'c': 'nullable'}",
                {'a': True, 'b': None, 'c': 'nullable'},
            ),
            ('null', None),
            ('not json and not python', 'not json and not python'),
            ("['unterminated'", "['unterminated'"),
            ({'k': 'v'}, {'k': 'v'}),
        ):
            with self.subTest(value):
                self.assertEqual(coerce_json_value(value), expected)

    def test_strict_schema(self):
        for schema, expected in (
            ('string', 'string'),
            ({'type': 'object', 'title': 'X'}, {'type': 'object', 'properties': {}}),
            (
                {
                    'type': 'object',
                    'additionalProperties': False,
                    'properties': {'a': {'type': ['null', 'integer'], 'default': 1}},
                },
                {'type': 'object', 'properties': {'a': {'type': 'integer'}}},
            ),
            (
                {'type': 'array', 'items': {'type': ['null']}, 'minItems': 1},
                {'type': 'array', 'items': {'type': 'string'}, 'minItems': 1},
            ),
            ({'type': 7}, {'type': 'string'}),
        ):
            with self.subTest(schema):
                self.assertEqual(to_strict_schema(schema), expected)

    def test_rate_limiter_slides_its_window(self):
        limiter = RateLimiter()
        self.assertTrue(all(limiter.check('free', 0, 60) for _i in range(5)))
        self.assertEqual(
            [limiter.check('a', 2, 60) for _i in range(3)], [True, True, False]
        )
        self.assertTrue(limiter.check('b', 2, 60))
        aged = time.monotonic() - 7200
        limiter._windows['a'] = collections.deque([aged, aged])
        self.assertTrue(limiter.check('a', 2, 60))
        limiter._windows['stale'] = collections.deque([aged])
        limiter._last_cleanup = aged
        limiter.check('b', 2, 60)
        self.assertNotIn('stale', limiter._windows)
        self.assertIn('a', limiter._windows)
