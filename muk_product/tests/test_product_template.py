from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestProductTemplate(TransactionCase):

    #----------------------------------------------------------
    # Tests
    #----------------------------------------------------------

    def test_manufacturer_code_compute_and_inverse_syncs_variant(self):
        template = self.env['product.template'].create({
            'name': 'Template',
        })
        variant = template.product_variant_id
        variant.manufacturer_code = 'VAR-001'
        template.invalidate_model(['manufacturer_code'])
        template._compute_manufacturer_code()
        self.assertEqual(template.manufacturer_code, 'VAR-001')
        template.manufacturer_code = 'TMP-002'
        template._inverse_manufacturer_code()
        variant.invalidate_model(['manufacturer_code'])
        self.assertEqual(variant.manufacturer_code, 'TMP-002')
