from odoo.exceptions import UserError
from odoo.tests import new_test_user

from odoo.addons.muk_product.tests.common import ProductCommon

GROUP_MENUS = {
    'group_product_variant': ['menu_product_product'],
    'group_product_pricelist': ['menu_salespricelists'],
    'group_uom': ['menu_uom_unit', 'menu_product_uom'],
    'group_show_uom_price': ['menu_product_base_unit'],
}


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

    def test_saving_the_toggles_switches_the_code_automation(self):
        settings = self.env['res.config.settings'].create(
            {
                'active_product_default_code_automation': False,
                'active_product_barcode_automation': False,
            }
        )
        settings.set_values()
        self.assertFalse(self.code_sequence.active)
        self.assertFalse(self.barcode_sequence.active)
        product = self.env['product.product'].create({'name': 'Unsequenced Product'})
        self.assertFalse(product.default_code)
        self.assertFalse(product.barcode)
        settings.write(
            {
                'active_product_default_code_automation': True,
                'active_product_barcode_automation': True,
            }
        )
        settings.set_values()
        self.assertTrue(self.code_sequence.active)
        self.assertTrue(self.barcode_sequence.active)

    def test_a_missing_sequence_reads_as_disabled_and_fails_on_save(self):
        self.code_sequence.unlink()
        settings = self.env['res.config.settings'].create({})
        self.assertFalse(settings.active_product_default_code_automation)
        self.assertTrue(settings.active_product_barcode_automation)
        with self.assertRaises(UserError):
            settings.set_values()

    def test_the_settings_unlock_the_product_menus(self):
        user = new_test_user(
            self.env, login='muk_product_menus', groups='base.group_user'
        )
        for enabled in (False, True):
            self.env['res.config.settings'].create(
                dict.fromkeys(GROUP_MENUS, enabled)
            ).execute()
            visible = self.env['ir.ui.menu'].with_user(user)._visible_menu_ids()
            for group, xmlids in GROUP_MENUS.items():
                for xmlid in xmlids:
                    with self.subTest(group=group, menu=xmlid, enabled=enabled):
                        menu = self.env.ref(f'muk_product.{xmlid}')
                        self.assertEqual(menu.id in visible, enabled)
        settings_menu = self.env.ref('muk_product.menu_product_config_settings')
        self.assertNotIn(settings_menu.id, visible)
        self.assertIn(settings_menu.id, self.env['ir.ui.menu']._visible_menu_ids())
