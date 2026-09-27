from odoo.tests import TransactionCase
from odoo.tools import mute_logger


class TestProductCodeUniqueness(TransactionCase):
    """Test that duplicate product references are refused with a usable error."""

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    @mute_logger('odoo.sql_db')
    def test_importing_a_duplicate_code_reports_a_usable_row_error(self):
        products = self.env['product.product']
        result = products.load(
            ['name', 'default_code'],
            [
                ['Uniq Import A', 'UNIQ-IMPORT-1'],
                ['Uniq Import B', 'UNIQ-IMPORT-1'],
                ['Uniq Import C', 'UNIQ-IMPORT-2'],
            ],
        )
        self.assertFalse(result['ids'])
        self.assertEqual(
            [(message['type'], message['message']) for message in result['messages']],
            [('error', 'Another entry with the same default code already exists.')],
        )
        self.assertFalse(
            products.search_count(
                [('default_code', 'in', ['UNIQ-IMPORT-1', 'UNIQ-IMPORT-2'])]
            )
        )
