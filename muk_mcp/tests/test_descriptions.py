from odoo.tests import common

from odoo.addons.muk_mcp.tools import descriptions


class TestSchemaDescriptions(common.TransactionCase):
    """Cover the shared JSON-schema fragment builders used by tool schemas."""

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_model_field(self):
        field = descriptions.model_field()
        self.assertEqual(field['type'], 'string')
        self.assertIn('res.partner', field['description'])

    def test_context_field_lists_examples(self):
        field = descriptions.context_field()
        self.assertEqual(field['type'], 'object')
        self.assertIn('active_test', field['description'])
        self.assertIn('allowed_company_ids', field['description'])

    def test_domain_field_without_note(self):
        field = descriptions.domain_field()
        self.assertEqual(field['type'], 'string')
        self.assertIn('is_company', field['description'])
        self.assertTrue(
            field['description'].endswith('Pass [] or omit for no filter.\n')
        )

    def test_domain_field_appends_note(self):
        field = descriptions.domain_field(extra_note="Used when 'ids' is absent.")
        self.assertTrue(field['description'].endswith("Used when 'ids' is absent."))

    def test_fields_field_defaults(self):
        field = descriptions.fields_field()
        self.assertEqual(field['type'], 'array')
        self.assertEqual(field['items'], {'type': 'string'})
        self.assertIn('ALWAYS specify this', field['description'])
        self.assertIn('["name", "email", "state"]', field['description'])

    def test_fields_field_without_required_hint(self):
        field = descriptions.fields_field(
            required_hint=False,
            example=['name', 'partner_id/name'],
            extra_note="Use '/' to traverse relations.",
        )
        self.assertNotIn('ALWAYS specify this', field['description'])
        self.assertIn("Use '/' to traverse relations.", field['description'])
        self.assertIn('partner_id/name', field['description'])

    def test_ids_field_uses_the_verb(self):
        field = descriptions.ids_field('permanently delete')
        self.assertEqual(field['items'], {'type': 'integer'})
        self.assertEqual(field['description'], 'Record IDs to permanently delete.')

    def test_ids_field_appends_note(self):
        field = descriptions.ids_field('call the method on', extra_note='Omit for X.')
        self.assertEqual(
            field['description'],
            'Record IDs to call the method on. Omit for X.',
        )
