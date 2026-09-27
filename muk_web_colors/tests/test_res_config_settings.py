from odoo.addons.muk_web_colors import _uninstall_cleanup
from odoo.addons.muk_web_colors.tests.common import ColorsCase


class TestResConfigSettings(ColorsCase):
    """Cover the light and dark color settings round trip."""

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_saving_unchanged_settings_keeps_the_module_files(self):
        settings = self.settings_model.create({})
        self.assertEqual(settings.color_brand_light, '#243742')
        self.assertEqual(settings.color_success_dark, '#1dc959')
        settings.execute()
        self.assertEqual(self._customization('light'), (0, 0))
        self.assertEqual(self._customization('dark'), (0, 0))

    def test_changing_a_color_customizes_only_its_palette(self):
        settings = self.settings_model.create({})
        settings.color_warning_dark = '#0D0E0F'
        settings.execute()
        self.assertEqual(self._customization('dark'), (1, 1))
        self.assertEqual(self._customization('light'), (0, 0))
        reloaded = self.settings_model.create({})
        self.assertEqual(reloaded.color_warning_dark, '#0D0E0F')
        self.assertEqual(reloaded.color_warning_light, '#ffac00')

    def test_reset_drops_only_its_palette(self):
        settings = self.settings_model.create({})
        settings.color_brand_light = '#0A0B0C'
        settings.color_brand_dark = '#0D0E0F'
        settings.execute()
        self.settings_model.create({}).action_reset_dark_color_assets()
        self.assertEqual(self._customization('dark'), (0, 0))
        reloaded = self.settings_model.create({})
        self.assertEqual(reloaded.color_brand_dark, '#243742')
        self.assertEqual(reloaded.color_brand_light, '#0A0B0C')
        reloaded.action_reset_light_color_assets()
        self.assertEqual(self._customization('light'), (0, 0))
        self.assertEqual(self.settings_model.create({}).color_brand_light, '#243742')

    def test_uninstall_drops_both_palettes(self):
        settings = self.settings_model.create({})
        settings.color_brand_light = '#0A0B0C'
        settings.color_brand_dark = '#0D0E0F'
        settings.execute()
        _uninstall_cleanup(self.env)
        self.assertEqual(self._customization('light'), (0, 0))
        self.assertEqual(self._customization('dark'), (0, 0))
