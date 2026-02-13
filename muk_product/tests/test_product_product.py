from unittest.mock import patch

from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestProductProduct(TransactionCase):

    #----------------------------------------------------------
    # Tests
    #----------------------------------------------------------

    def test_create_sets_default_code_and_barcode_when_missing(self):
        with patch.object(
            type(self.env['product.product']),
            '_get_next_default_code',
            autospec=True,
            return_value='REF00001',
        ), patch.object(
            type(self.env['product.product']),
            '_get_next_barcode',
            autospec=True,
            return_value='1234567890128',
        ):
            product = self.env['product.product'].create({
                'name': 'Auto Codes',
            })

        self.assertEqual(product.default_code, 'REF00001')
        self.assertEqual(product.barcode, '1234567890128')

    def test_fixed_price_updates_price_extra_and_price_string(self):
        product = self.env['product.product'].create({
            'name': 'Fixed Price',
            'list_price': 10.0,
            'fixed_price': 12.5,
        })
        product._compute_product_price_extra()
        product._compute_price_string()
        self.assertAlmostEqual(product.price_extra, 2.5)
        self.assertTrue(product.price_string)
        self.assertIn('=', product.price_string)
        self.assertIn('+', product.price_string)

    def test_search_display_name_includes_manufacturer_code(self):
        product = self.env['product.product'].create({
            'name': 'Searchable',
            'manufacturer_code': 'MUK-M123',
        })
        domain = self.env['product.product']._search_display_name(
            'ilike',
            'MUK-M123',
        )
        found = self.env['product.product'].search(domain)
        self.assertIn(product, found)
