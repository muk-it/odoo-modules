from __future__ import annotations

from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestProductDisplayNameSearch(TransactionCase):
    """Cover the manufacturer code extension of the display-name search."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.acme = cls.env['product.product'].create(
            {
                'name': 'Acme Widget',
                'manufacturer_code': 'MUK-M123',
            }
        )
        cls.globex = cls.env['product.product'].create(
            {
                'name': 'Globex Gadget',
                'manufacturer_code': 'GLX-999',
            }
        )

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_searching_a_manufacturer_code_finds_only_that_product(self):
        found = self.env['product.product'].search(
            [('display_name', 'ilike', 'MUK-M123')]
        )
        self.assertIn(self.acme, found)
        self.assertNotIn(self.globex, found)

    def test_a_partial_manufacturer_code_still_matches(self):
        found = self.env['product.product'].search(
            [('display_name', 'ilike', 'uk-m12')]
        )
        self.assertIn(self.acme, found)
        self.assertNotIn(self.globex, found)

    def test_searching_a_product_name_still_works(self):
        found = self.env['product.product'].search(
            [('display_name', 'ilike', 'Globex Gadget')]
        )
        self.assertIn(self.globex, found)
        self.assertNotIn(self.acme, found)

    def test_searching_an_internal_reference_still_works(self):
        found = self.env['product.product'].search(
            [('display_name', 'ilike', self.acme.default_code)]
        )
        self.assertIn(self.acme, found)

    def test_a_negative_search_excludes_the_manufacturer_code_match(self):
        found = self.env['product.product'].search(
            [('display_name', 'not ilike', 'MUK-M123')]
        )
        self.assertNotIn(self.acme, found)
        self.assertIn(self.globex, found)

    def test_an_unmatched_manufacturer_code_returns_nothing_of_ours(self):
        found = self.env['product.product'].search(
            [('display_name', 'ilike', 'NO-SUCH-CODE')]
        )
        self.assertNotIn(self.acme, found)
        self.assertNotIn(self.globex, found)

    def test_the_manufacturer_code_search_handles_unicode(self):
        product = self.env['product.product'].create(
            {
                'name': 'Unicode Product',
                'manufacturer_code': 'MÜK-Ünïcodé-☂',
            }
        )
        found = self.env['product.product'].search(
            [('display_name', 'ilike', 'Ünïcodé')]
        )
        self.assertIn(product, found)
