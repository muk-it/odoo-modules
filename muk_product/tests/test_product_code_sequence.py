from __future__ import annotations

from unittest.mock import patch

from odoo.tests.common import tagged

from .common import ProductCommon


@tagged('post_install', '-at_install')
class TestProductCodeSequence(ProductCommon):
    """Cover the internal reference and barcode sequence helpers."""

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def next_barcode_for(self, sequence_value: str) -> str:
        """Return the barcode built for a fixed ``ir.sequence`` value.

        :param sequence_value: the raw value the sequence is made to return
        :return: the barcode including the appended check digit
        """
        with patch.object(
            type(self.env['ir.sequence']),
            'next_by_code',
            return_value=sequence_value,
        ):
            return self.env['product.product']._get_next_barcode()

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_next_default_code_is_padded_and_never_repeats(self):
        variants = self.env['product.product']
        codes = [variants._get_next_default_code() for _ in range(3)]
        self.assertEqual(len(set(codes)), 3)
        for code in codes:
            self.assertEqual(len(code), 8)
            self.assertTrue(code.isdigit())

    def test_next_barcode_appends_a_valid_ean13_check_digit(self):
        variants = self.env['product.product']
        barcodes = [variants._get_next_barcode() for _ in range(3)]
        self.assertEqual(len(set(barcodes)), 3)
        for barcode in barcodes:
            self.assertEqual(len(barcode), 13)
            self.assert_valid_barcode(barcode)

    def test_next_barcode_check_digit_matches_a_known_ean13(self):
        self.assertEqual(self.next_barcode_for('400638133393'), '4006381333931')

    def test_next_barcode_check_digit_is_zero_for_an_all_zero_payload(self):
        self.assertEqual(self.next_barcode_for('000000000000'), '0000000000000')

    def test_next_barcode_handles_a_single_digit_payload(self):
        self.assertEqual(self.next_barcode_for('7'), '79')

    def test_next_barcode_handles_a_two_digit_payload(self):
        self.assertEqual(self.next_barcode_for('12'), '123')

    def test_an_inactive_sequence_yields_no_code(self):
        (self.code_sequence + self.barcode_sequence).write({'active': False})
        variants = self.env['product.product']
        self.assertFalse(variants._get_next_default_code())
        self.assertFalse(variants._get_next_barcode())
