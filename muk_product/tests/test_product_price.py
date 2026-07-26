from odoo.tests.common import tagged
from odoo.tools import format_amount

from .common import ProductCommon


@tagged('post_install', '-at_install')
class TestProductPrice(ProductCommon):
    """Cover the fixed variant price and the formatted price string."""

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_a_fixed_price_drives_the_price_extra(self):
        product = self.env['product.product'].create(
            {
                'name': 'Fixed Price',
                'list_price': 10.0,
                'fixed_price': 12.5,
            }
        )
        self.assertAlmostEqual(product.price_extra, 2.5)
        self.assertAlmostEqual(product.lst_price, 12.5)

    def test_a_fixed_price_below_the_list_price_gives_a_negative_extra(self):
        product = self.env['product.product'].create(
            {
                'name': 'Discounted Variant',
                'list_price': 10.0,
                'fixed_price': 7.5,
            }
        )
        self.assertAlmostEqual(product.price_extra, -2.5)
        self.assertAlmostEqual(product.lst_price, 7.5)

    def test_the_price_extra_tracks_the_current_list_price(self):
        product = self.env['product.product'].create(
            {
                'name': 'Moving List Price',
                'list_price': 10.0,
                'fixed_price': 12.5,
            }
        )
        self.assertAlmostEqual(product.price_extra, 2.5)
        product.product_tmpl_id.list_price = 20.0
        product.invalidate_recordset(['price_extra'])
        self.assertAlmostEqual(product.price_extra, -7.5)

    def test_without_a_fixed_price_the_attribute_extra_is_kept(self):
        template = self.create_variant_template('Table', ['Oak', 'Teak'])
        template.list_price = 100.0
        teak_value = template.attribute_line_ids.product_template_value_ids.filtered(
            lambda ptav: ptav.product_attribute_value_id.name == 'Teak'
        )
        teak_value.price_extra = 30.0
        variant = template.product_variant_ids.filtered(
            lambda product: teak_value in product.product_template_attribute_value_ids
        )
        self.assertAlmostEqual(variant.price_extra, 30.0)
        variant.fixed_price = 150.0
        self.assertAlmostEqual(variant.price_extra, 50.0)
        variant.fixed_price = 0.0
        self.assertAlmostEqual(variant.price_extra, 30.0)

    def test_the_price_string_joins_the_list_price_and_the_extra(self):
        product = self.env['product.product'].create(
            {
                'name': 'Price String',
                'list_price': 10.0,
                'fixed_price': 12.5,
            }
        )
        currency = product.currency_id
        list_price = format_amount(self.env, 10.0, currency)
        price_extra = format_amount(self.env, 2.5, currency)
        self.assertEqual(product.price_string, f'(= {list_price} + {price_extra})')

    def test_the_price_string_follows_the_list_price(self):
        product = self.env['product.product'].create(
            {
                'name': 'Reactive Price String',
                'list_price': 10.0,
            }
        )
        first = product.price_string
        product.product_tmpl_id.list_price = 42.0
        self.assertNotEqual(product.price_string, first)
        self.assertIn(
            format_amount(self.env, 42.0, product.currency_id),
            product.price_string,
        )

    def test_the_price_string_formats_both_amounts_in_the_given_currency(self):
        currency = self.env.ref('base.JPY')
        list_price = format_amount(self.env, 1000.0, currency)
        price_extra = format_amount(self.env, 250.0, currency)
        self.assertEqual(
            self.env['product.product']._construct_price_string(
                currency, 1000.0, 250.0
            ),
            f'(= {list_price} + {price_extra})',
        )
