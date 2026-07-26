from odoo.tests import common

from odoo.addons.muk_mcp.tools import schema


class TestStrictSchema(common.TransactionCase):
    """Cover the strict JSON-schema reduction applied to every tool listing."""

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_non_dict_passes_through_unchanged(self):
        self.assertEqual(schema.to_strict_schema('string'), 'string')
        self.assertEqual(schema.to_strict_schema([1, 2]), [1, 2])
        self.assertIsNone(schema.to_strict_schema(None))

    def test_unknown_keys_are_stripped(self):
        result = schema.to_strict_schema(
            {
                'type': 'string',
                'description': 'A field.',
                'additionalProperties': False,
                'title': 'Ignored',
            },
        )
        self.assertEqual(result, {'type': 'string', 'description': 'A field.'})

    def test_default_key_is_stripped(self):
        result = schema.to_strict_schema({'type': 'integer', 'default': 80})
        self.assertEqual(result, {'type': 'integer'})

    def test_object_type_gains_empty_properties(self):
        self.assertEqual(
            schema.to_strict_schema({'type': 'object'}),
            {'type': 'object', 'properties': {}},
        )

    def test_existing_properties_are_kept(self):
        result = schema.to_strict_schema(
            {
                'type': 'object',
                'properties': {'name': {'type': 'string'}},
            },
        )
        self.assertEqual(result['properties'], {'name': {'type': 'string'}})

    def test_nested_properties_are_reduced_recursively(self):
        result = schema.to_strict_schema(
            {
                'type': 'object',
                'properties': {
                    'inner': {
                        'type': ['string', 'null'],
                        'default': 'x',
                        'title': 'Ignored',
                    },
                },
            },
        )
        self.assertEqual(result['properties']['inner'], {'type': 'string'})

    def test_items_are_reduced_recursively(self):
        result = schema.to_strict_schema(
            {
                'type': 'array',
                'items': {'type': 'object', 'title': 'Ignored'},
            },
        )
        self.assertEqual(result['items'], {'type': 'object', 'properties': {}})

    def test_normalize_type_picks_first_non_null_entry(self):
        self.assertEqual(schema._normalize_type(['string', 'null']), 'string')
        self.assertEqual(schema._normalize_type(['null', 'integer']), 'integer')

    def test_normalize_type_falls_back_to_string(self):
        self.assertEqual(schema._normalize_type(['null']), 'string')
        self.assertEqual(schema._normalize_type([]), 'string')
        self.assertEqual(schema._normalize_type(None), 'string')
        self.assertEqual(schema._normalize_type(7), 'string')
        self.assertEqual(schema._normalize_type({'type': 'string'}), 'string')
