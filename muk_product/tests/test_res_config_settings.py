from odoo.exceptions import UserError
from odoo.tests.common import tagged

from .common import ProductCommon

CODE_XMLID = 'muk_product.seq_product_reference'
BARCODE_XMLID = 'muk_product.seq_product_barcode'


@tagged('post_install', '-at_install')
class TestResConfigSettings(ProductCommon):
    """Cover the product reference and barcode automation toggles."""

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_the_toggles_mirror_the_sequence_state(self):
        self.barcode_sequence.active = False
        settings = self.env['res.config.settings'].create({})
        self.assertTrue(settings.active_product_default_code_automation)
        self.assertFalse(settings.active_product_barcode_automation)

    def test_saving_the_toggles_switches_the_sequences(self):
        settings = self.env['res.config.settings'].create({})
        settings.write(
            {
                'active_product_default_code_automation': False,
                'active_product_barcode_automation': False,
            }
        )
        settings.set_values()
        self.assertFalse(self.code_sequence.active)
        self.assertFalse(self.barcode_sequence.active)
        settings.write(
            {
                'active_product_default_code_automation': True,
                'active_product_barcode_automation': True,
            }
        )
        settings.set_values()
        self.assertTrue(self.code_sequence.active)
        self.assertTrue(self.barcode_sequence.active)

    def test_switching_the_toggles_off_stops_the_code_automation(self):
        settings = self.env['res.config.settings'].create({})
        settings.write(
            {
                'active_product_default_code_automation': False,
                'active_product_barcode_automation': False,
            }
        )
        settings.set_values()
        product = self.env['product.product'].create({'name': 'Unsequenced Product'})
        self.assertFalse(product.default_code)
        self.assertFalse(product.barcode)

    def test_a_missing_sequence_reports_a_user_error_on_save(self):
        self.env.ref(CODE_XMLID).unlink()
        settings = self.env['res.config.settings'].create({})
        with self.assertRaises(UserError):
            settings.set_values()

    def test_a_missing_sequence_reads_as_a_disabled_automation(self):
        self.env.ref(BARCODE_XMLID).unlink()
        settings = self.env['res.config.settings']
        self.assertFalse(settings._get_product_sequence_active(BARCODE_XMLID))
        self.assertFalse(settings._get_product_sequence_active('muk_product.unknown'))

    def test_setting_an_unknown_sequence_reports_a_user_error(self):
        with self.assertRaises(UserError):
            self.env['res.config.settings']._set_product_sequence_active(
                'muk_product.unknown', True
            )
