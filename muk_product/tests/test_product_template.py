from odoo.tests import TransactionCase


class TestProductTemplate(TransactionCase):
    """Cover the manufacturer field sync between template and variant."""

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_the_template_mirrors_the_code_of_its_single_variant(self):
        template = self.env['product.template'].create({'name': 'Single Variant'})
        template.product_variant_id.manufacturer_code = 'VAR-001'
        self.assertEqual(template.manufacturer_code, 'VAR-001')

    def test_writing_the_template_code_reaches_its_single_variant(self):
        template = self.env['product.template'].create({'name': 'Single Variant'})
        template.manufacturer_code = 'TMP-002'
        self.assertEqual(template.product_variant_id.manufacturer_code, 'TMP-002')
        self.assertEqual(template.manufacturer_code, 'TMP-002')

    def test_creating_a_template_with_a_code_reaches_its_variant(self):
        template = self.env['product.template'].create(
            {
                'name': 'Created With Code',
                'manufacturer_code': 'NEW-003',
            }
        )
        self.assertEqual(template.product_variant_id.manufacturer_code, 'NEW-003')
        self.assertEqual(template.manufacturer_code, 'NEW-003')
