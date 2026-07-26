from __future__ import annotations

from psycopg2 import IntegrityError

from odoo.tests.common import TransactionCase, tagged
from odoo.tools import mute_logger


@tagged('post_install', '-at_install')
class TestProductCodeUniqueness(TransactionCase):
    """Test that duplicate product references are refused with a usable error."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.Product = cls.env['product.product']

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _create_without_automation(self, **values) -> None:
        """Create a variant without the automatic reference assignment."""
        self.Product.with_context(skip_product_code_automation=True).create(
            {'name': 'Uniqueness Product', **values}
        )

    def _duplicate_error_message(self, field: str, code: str) -> str:
        """Return the user-facing message a duplicate reference produces."""
        self.Product.create({'name': 'Uniqueness First', field: code})
        with (
            mute_logger('odoo.sql_db'),
            self.assertRaises(IntegrityError) as caught,
            self.env.cr.savepoint(),
        ):
            self.Product.create({'name': 'Uniqueness Second', field: code})
            self.env.flush_all()
        return self.Product._sql_error_to_message(caught.exception)

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_duplicate_default_code_reports_our_own_message(self):
        message = self._duplicate_error_message('default_code', 'UNIQ-CODE-1')
        self.assertEqual(
            message, 'Another entry with the same default code already exists.'
        )

    def test_duplicate_barcode_reports_our_own_message(self):
        message = self._duplicate_error_message('barcode', 'UNIQ-BARCODE-1')
        self.assertEqual(message, 'Another entry with the same barcode already exists.')

    def test_importing_a_duplicate_code_reports_a_usable_row_error(self):
        result = self.Product.load(
            ['name', 'default_code'],
            [
                ['Uniq Import A', 'UNIQ-IMPORT-1'],
                ['Uniq Import B', 'UNIQ-IMPORT-1'],
                ['Uniq Import C', 'UNIQ-IMPORT-2'],
            ],
        )
        self.assertFalse(result['ids'])
        self.assertEqual(len(result['messages']), 1)
        message = result['messages'][0]
        self.assertEqual(message['type'], 'error')
        self.assertEqual(
            message['message'],
            'Another entry with the same default code already exists.',
        )
        self.assertNotIn('IntegrityError', message['message'])
        self.assertFalse(
            self.Product.search_count(
                [('default_code', 'in', ['UNIQ-IMPORT-1', 'UNIQ-IMPORT-2'])]
            )
        )

    def test_importing_distinct_codes_succeeds(self):
        result = self.Product.load(
            ['name', 'default_code'],
            [
                ['Uniq Clean A', 'UNIQ-CLEAN-1'],
                ['Uniq Clean B', 'UNIQ-CLEAN-2'],
            ],
        )
        self.assertEqual(len(result['ids']), 2)
        self.assertFalse([m for m in result['messages'] if m['type'] == 'error'])

    def test_missing_references_never_collide(self):
        self._create_without_automation(default_code=False, barcode=False)
        self._create_without_automation(default_code=False, barcode=False)
        self.env.flush_all()
        self.assertEqual(
            self.Product.search_count(
                [
                    ('name', '=', 'Uniqueness Product'),
                    ('default_code', '=', False),
                ]
            ),
            2,
        )

    def test_automatic_references_are_unique_across_a_batch(self):
        products = self.Product.create(
            [{'name': f'Uniqueness Batch {index}'} for index in range(5)]
        )
        self.env.flush_all()
        self.assertEqual(len(set(products.mapped('default_code'))), 5)
        self.assertEqual(len(set(products.mapped('barcode'))), 5)
        self.assertTrue(all(products.mapped('default_code')))
        self.assertTrue(all(products.mapped('barcode')))
