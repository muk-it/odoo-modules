from __future__ import annotations

from odoo.tests.common import TransactionCase, tagged

from odoo.addons.muk_ai_enterprise.tools import adapter


@tagged('post_install', '-at_install', 'muk_ai_enterprise')
class TestAdapter(TransactionCase):
    """Cover the pure EE bridge adapter helpers."""

    # ----------------------------------------------------------
    # Tests coerce_schema
    # ----------------------------------------------------------

    def test_coerce_schema_normalizes_every_input(self):
        cases = (
            (None, {'type': 'object', 'properties': {}}),
            ('', {'type': 'object', 'properties': {}}),
            ('not json at all', {'type': 'object', 'properties': {}}),
            ('[1, 2, 3]', {'type': 'object', 'properties': {}}),
            ('"a string"', {'type': 'object', 'properties': {}}),
            ('{}', {'type': 'object', 'properties': {}}),
            (
                '{"properties": {"msg": {"type": "string"}}}',
                {'type': 'object', 'properties': {'msg': {'type': 'string'}}},
            ),
            (
                '{"type": "object", "properties": {}, "required": ["msg"]}',
                {'type': 'object', 'properties': {}, 'required': ['msg']},
            ),
        )
        for schema_text, expected in cases:
            with self.subTest(schema_text=schema_text):
                self.assertEqual(adapter.coerce_schema(schema_text), expected)

    def test_coerce_schema_never_hands_out_the_module_default(self):
        schema = adapter.coerce_schema(None)
        self.assertIsNot(schema, adapter.EMPTY_SCHEMA)
        schema['required'] = ['injected']
        self.assertNotIn('required', adapter.coerce_schema(None))

    # ----------------------------------------------------------
    # Tests serialize_result
    # ----------------------------------------------------------

    def test_serialize_result_renders_transport_strings(self):
        self.assertEqual(adapter.serialize_result(None), '')
        self.assertEqual(adapter.serialize_result(''), '')
        self.assertEqual(adapter.serialize_result('echoed'), 'echoed')
        self.assertEqual(adapter.serialize_result({'id': 7}), '{"id": 7}')
        self.assertEqual(adapter.serialize_result([1, 2]), '[1, 2]')

    def test_serialize_result_survives_unserializable_values(self):
        record = self.env.user
        self.assertIn('res.users', adapter.serialize_result(record))
        circular = {}
        circular['self'] = circular
        self.assertTrue(adapter.serialize_result(circular))

    # ----------------------------------------------------------
    # Tests render_init_context
    # ----------------------------------------------------------

    def test_render_init_context_wraps_only_real_items(self):
        self.assertEqual(adapter.render_init_context(None), '')
        self.assertEqual(adapter.render_init_context({}), '')
        self.assertEqual(adapter.render_init_context({'kind': 'record'}), '')
        self.assertEqual(adapter.render_init_context({'ee_init_context': []}), '')
        self.assertEqual(adapter.render_init_context('not a dict'), '')
        self.assertEqual(
            adapter.render_init_context({'ee_init_context': ['one', 'two']}),
            '<ee_ctx>\none\ntwo\n</ee_ctx>',
        )

    # ----------------------------------------------------------
    # Tests action_tool_name
    # ----------------------------------------------------------

    def test_action_tool_name_prefers_the_technical_xml_id(self):
        self.assertEqual(
            adapter.action_tool_name(42, 'my_module.send_quote'),
            'ee_action_send_quote',
        )

    def test_action_tool_name_falls_back_to_the_database_id(self):
        self.assertEqual(adapter.action_tool_name(42, None), 'ee_action_action_42')
        self.assertEqual(adapter.action_tool_name(42, ''), 'ee_action_action_42')
        self.assertEqual(
            adapter.action_tool_name(42, 'no_module_part'),
            'ee_action_action_42',
        )
