from odoo.tests.common import tagged

from .common import ProductCommon


@tagged('post_install', '-at_install')
class TestProductCodeAutomation(ProductCommon):
    """Cover the automatic internal reference and barcode assignment."""

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_variant_creation_assigns_both_codes_from_the_sequences(self):
        product = self.env['product.product'].create({'name': 'Auto Codes'})
        self.assertEqual(len(product.default_code), 8)
        self.assertTrue(product.default_code.isdigit())
        self.assert_valid_barcode(product.barcode)

    def test_variant_creation_keeps_the_provided_codes(self):
        product = self.env['product.product'].create(
            {
                'name': 'Manual Codes',
                'default_code': 'MANUAL-REF',
                'barcode': '4006381333931',
            }
        )
        self.assertEqual(product.default_code, 'MANUAL-REF')
        self.assertEqual(product.barcode, '4006381333931')

    def test_skip_context_leaves_both_codes_empty(self):
        product = (
            self.env['product.product']
            .with_context(skip_product_code_automation=True)
            .create({'name': 'No Codes'})
        )
        self.assertFalse(product.default_code)
        self.assertFalse(product.barcode)

    def test_template_creation_assigns_codes_to_its_variant(self):
        template = self.env['product.template'].create({'name': 'Auto Template'})
        variant = template.product_variant_id
        self.assertTrue(variant.default_code)
        self.assert_valid_barcode(variant.barcode)
        self.assertEqual(template.default_code, variant.default_code)
        self.assertEqual(template.barcode, variant.barcode)

    def test_template_creation_keeps_the_provided_codes(self):
        template = self.env['product.template'].create(
            {
                'name': 'Manual Template',
                'default_code': 'TMPL-REF',
                'barcode': '4006381333931',
            }
        )
        self.assertEqual(template.product_variant_id.default_code, 'TMPL-REF')
        self.assertEqual(template.product_variant_id.barcode, '4006381333931')

    def test_batch_template_creation_assigns_distinct_codes(self):
        templates = self.env['product.template'].create(
            [{'name': f'Batch {index}'} for index in range(3)]
        )
        variants = templates.product_variant_ids
        self.assertEqual(len(variants), 3)
        self.assertEqual(len(set(variants.mapped('default_code'))), 3)
        self.assertEqual(len(set(variants.mapped('barcode'))), 3)
        for barcode in variants.mapped('barcode'):
            self.assert_valid_barcode(barcode)

    def test_every_generated_variant_gets_its_own_codes(self):
        template = self.create_variant_template('Shirt', ['Red', 'Blue', 'Green'])
        variants = template.product_variant_ids
        self.assertEqual(len(variants), 3)
        self.assertTrue(all(variants.mapped('default_code')))
        self.assertEqual(len(set(variants.mapped('default_code'))), 3)
        self.assertEqual(len(set(variants.mapped('barcode'))), 3)

    def test_a_variant_added_later_gets_its_own_codes(self):
        template = self.create_variant_template('Mug', ['Small', 'Medium'])
        attribute = template.attribute_line_ids.attribute_id
        large = self.env['product.attribute.value'].create(
            {
                'name': 'Large',
                'attribute_id': attribute.id,
            }
        )
        existing = template.product_variant_ids
        template.attribute_line_ids.write({'value_ids': [(4, large.id)]})
        added = template.product_variant_ids - existing
        self.assertEqual(len(added), 1)
        self.assertTrue(added.default_code)
        self.assert_valid_barcode(added.barcode)
        self.assertNotIn(added.default_code, existing.mapped('default_code'))

    def test_duplicating_a_template_generates_fresh_codes(self):
        template = self.env['product.template'].create(
            {
                'name': 'Original',
                'manufacturer_name': 'ACME Widget',
            }
        )
        copied = template.copy()
        self.assertTrue(copied.default_code)
        self.assertNotEqual(copied.default_code, template.default_code)
        self.assertNotEqual(copied.barcode, template.barcode)
        self.assert_valid_barcode(copied.barcode)
        self.assertEqual(copied.manufacturer_name, 'ACME Widget')

    def test_assign_missing_codes_only_fills_the_empty_one(self):
        product = (
            self.env['product.product']
            .with_context(skip_product_code_automation=True)
            .create(
                {
                    'name': 'Half Coded',
                    'barcode': '4006381333931',
                }
            )
        )
        product._assign_missing_product_codes()
        self.assertEqual(product.barcode, '4006381333931')
        self.assertTrue(product.default_code)

    def test_switching_off_the_barcode_sequence_keeps_the_reference(self):
        self.barcode_sequence.write({'active': False})
        product = self.env['product.product'].create({'name': 'Reference Only'})
        self.assertTrue(product.default_code)
        self.assertFalse(product.barcode)
