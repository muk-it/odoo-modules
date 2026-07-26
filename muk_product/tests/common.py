from __future__ import annotations

from odoo import models
from odoo.tests.common import TransactionCase


class ProductCommon(TransactionCase):
    """Shared fixtures for the automatic product code and price tests."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.code_sequence = cls.env.ref('muk_product.seq_product_reference')
        cls.barcode_sequence = cls.env.ref('muk_product.seq_product_barcode')
        (cls.code_sequence + cls.barcode_sequence).write({'active': True})

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @staticmethod
    def check_digit(payload: str) -> str:
        """Return the GTIN check digit for ``payload``, weighting from the right.

        :param payload: the barcode digits without the trailing check digit
        :return: the single check digit as a string
        """
        total = sum(
            int(digit) * (3 if index % 2 == 0 else 1)
            for index, digit in enumerate(reversed(payload))
        )
        return str((10 - total % 10) % 10)

    def assert_valid_barcode(self, barcode: str) -> None:
        """Assert ``barcode`` is all digits and carries a valid check digit."""
        self.assertTrue(barcode)
        self.assertTrue(barcode.isdigit(), f'{barcode} is not numeric')
        self.assertEqual(barcode[-1], self.check_digit(barcode[:-1]))

    def create_variant_template(self, name: str, values: list[str]) -> models.BaseModel:
        """Create a template carrying one attribute line with ``values``.

        :param name: the template name
        :param values: the attribute value names to generate variants for
        :return: the created ``product.template`` record
        """
        attribute = self.env['product.attribute'].create(
            {
                'name': f'{name} Attribute',
                'create_variant': 'always',
                'value_ids': [(0, 0, {'name': value}) for value in values],
            }
        )
        return self.env['product.template'].create(
            {
                'name': name,
                'attribute_line_ids': [
                    (
                        0,
                        0,
                        {
                            'attribute_id': attribute.id,
                            'value_ids': [(6, 0, attribute.value_ids.ids)],
                        },
                    )
                ],
            }
        )
