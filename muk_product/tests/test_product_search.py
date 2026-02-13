import ast

from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestProductSearch(TransactionCase):

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_compute_search_domain_match_uses_in_operator(self):
        wizard = self.env['muk_product.product_search'].create({
            'search_value': 'REF00001\nREF00002',
            'value_split_operator': '\n',
            'search_operator': '=',
            'search_field': 'product_variant_ids.default_code',
        })
        wizard._compute_search_domain()
        self.assertEqual(
            ast.literal_eval(wizard.search_domain),
            [('product_variant_ids.default_code', 'in', ['REF00001', 'REF00002'])],
        )

    def test_action_search_products_sets_action_domain(self):
        template_a = self.env['product.template'].create({'name': 'Alpha'})
        template_b = self.env['product.template'].create({'name': 'Beta'})
        template_c = self.env['product.template'].create({'name': 'Gamma'})
        wizard = self.env['muk_product.product_search'].create({
            'search_value': 'Alpha\nBeta',
            'value_split_operator': '\n',
            'search_operator': 'ilike',
            'search_field': 'name',
        })
        wizard._compute_search_domain()
        action = wizard.action_search_products()
        domain = action['domain']
        found = self.env['product.template'].search(domain)
        self.assertIn(template_a, found)
        self.assertIn(template_b, found)
        self.assertNotIn(template_c, found)

    def test_product_preview_shows_max_7_and_sets_hint_when_more(self):
        codes, templates = [], self.env['product.template']
        for i in range(1, 9):
            template = self.env['product.template'].create({
                'name': f'Template {i}',
            })
            template.product_variant_id.default_code = f'CODE{i}'
            templates |= template
            codes.append(f'CODE{i}')

        wizard = self.env['muk_product.product_search'].create({
            'search_value': '\n'.join(codes),
            'value_split_operator': '\n',
            'search_operator': '=',
            'search_field': 'product_variant_ids.default_code',
        })
        wizard._compute_search_domain()
        wizard._compute_product_preview()
        self.assertEqual(len(wizard.product_preview_ids), 7)
        self.assertTrue(wizard.product_preview_hint)
