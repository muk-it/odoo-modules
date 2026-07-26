from odoo.tests.common import tagged

from .common import ProductCommon


@tagged('post_install', '-at_install')
class TestProductTemplate(ProductCommon):
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

    def test_a_multi_variant_template_exposes_no_manufacturer_code(self):
        template = self.create_variant_template('Cap', ['Small', 'Large'])
        template.product_variant_ids[0].manufacturer_code = 'ONE-004'
        self.assertFalse(template.manufacturer_code)

    def test_writing_the_code_on_a_multi_variant_template_changes_nothing(self):
        template = self.create_variant_template('Hat', ['Small', 'Large'])
        template.manufacturer_code = 'MANY-005'
        self.assertFalse(any(template.product_variant_ids.mapped('manufacturer_code')))

    def test_the_manufacturer_details_survive_a_duplication(self):
        manufacturer = self.env['res.partner'].create({'name': 'ACME Industries'})
        template = self.env['product.template'].create(
            {
                'name': 'Branded Product',
                'manufacturer_id': manufacturer.id,
                'manufacturer_name': 'ACME Super Widget',
                'manufacturer_url': 'https://example.com/acme-super-widget',
            }
        )
        copied = template.copy()
        self.assertEqual(copied.manufacturer_id, manufacturer)
        self.assertEqual(copied.manufacturer_name, 'ACME Super Widget')
        self.assertEqual(
            copied.manufacturer_url, 'https://example.com/acme-super-widget'
        )

    def test_the_manufacturer_code_is_searchable_from_the_template(self):
        template = self.env['product.template'].create(
            {
                'name': 'Searchable Template',
                'manufacturer_code': 'FIND-006',
            }
        )
        found = self.env['product.template'].search(
            [('product_variant_ids.manufacturer_code', '=', 'FIND-006')]
        )
        self.assertIn(template, found)
