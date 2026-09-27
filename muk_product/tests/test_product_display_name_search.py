from odoo.tests import TransactionCase


class TestProductDisplayNameSearch(TransactionCase):
    """Cover the manufacturer code extension of the display-name search."""

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_the_display_name_search_matches_the_manufacturer_code(self):
        products = self.env['product.product']
        acme = products.create({'name': 'Acme Widget', 'manufacturer_code': 'MUK-M123'})
        globex = products.create(
            {'name': 'Globex Gadget', 'manufacturer_code': 'GLX-999'}
        )
        cases = [
            ('ilike', 'MUK-M123', acme),
            ('ilike', 'uk-m12', acme),
            ('ilike', 'Globex Gadget', globex),
            ('ilike', acme.default_code, acme),
            ('ilike', 'NO-SUCH-CODE', products),
            ('not ilike', 'MUK-M123', globex),
        ]
        for operator, value, expected in cases:
            with self.subTest(operator=operator, value=value):
                found = products.search(
                    [
                        ('display_name', operator, value),
                        ('id', 'in', (acme + globex).ids),
                    ]
                )
                self.assertEqual(found, expected)
