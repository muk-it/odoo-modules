from __future__ import annotations

from odoo.tests import TransactionCase


class TestResConfigSettings(TransactionCase):
    """Cover the appsbar theme color settings round trip."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        """Resolve the customized asset URL of every color palette."""
        super().setUpClass()
        cls.settings_model = cls.env['res.config.settings']
        cls.editor = cls.env['muk_web_colors.color_assets_editor']
        cls.custom_urls = {
            palette: cls.editor._get_custom_colors_url(url, bundle)
            for palette, (
                url,
                bundle,
                _names,
            ) in cls.settings_model.COLOR_ASSETS.items()
        }

    def setUp(self) -> None:
        """Drop every customized color asset left by an earlier test."""
        super().setUp()
        for custom_url in self.custom_urls.values():
            self.env['ir.attachment'].search([('url', '=', custom_url)]).unlink()
            self.env['ir.asset'].search([('path', '=', custom_url)]).unlink()

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _is_customized(self, palette: str) -> bool:
        """Return whether a customized color attachment exists for a palette."""
        return bool(
            self.env['ir.attachment'].search([('url', '=', self.custom_urls[palette])])
        )

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_both_appsbar_palettes_are_registered(self):
        assets = self.settings_model.COLOR_ASSETS
        names = (
            'color_appbar_text',
            'color_appbar_active',
            'color_appbar_background',
        )
        self.assertEqual(
            assets['theme_light'],
            (
                '/muk_web_enterprise_theme/static/src/colors/light/light.scss',
                'web._assets_primary_variables',
                names,
            ),
        )
        self.assertEqual(
            assets['theme_dark'],
            (
                '/muk_web_enterprise_theme/static/src/colors/dark/dark.scss',
                'web.assets_web_dark',
                names,
            ),
        )

    def test_settings_expose_the_theme_asset_defaults(self):
        settings = self.settings_model.create({})
        self.assertEqual(settings.color_appbar_text_theme_light, '#dee2e6')
        self.assertEqual(settings.color_appbar_active_theme_light, '#5d8da8')
        self.assertEqual(settings.color_appbar_background_theme_light, '#111827')
        self.assertEqual(settings.color_appbar_text_theme_dark, '#e4e4e4')
        self.assertEqual(settings.color_appbar_active_theme_dark, '#5d8da8')
        self.assertEqual(settings.color_appbar_background_theme_dark, '#3c3e4b')

    def test_saving_without_a_change_creates_no_customization(self):
        self.settings_model.create({}).execute()
        self.assertFalse(self._is_customized('theme_light'))
        self.assertFalse(self._is_customized('theme_dark'))

    def test_changing_a_light_theme_color_customizes_only_the_light_asset(self):
        settings = self.settings_model.create({})
        settings.color_appbar_text_theme_light = '#123456'
        settings.execute()
        self.assertTrue(self._is_customized('theme_light'))
        self.assertFalse(self._is_customized('theme_dark'))
        reloaded = self.settings_model.create({})
        self.assertEqual(reloaded.color_appbar_text_theme_light, '#123456')
        self.assertEqual(reloaded.color_appbar_text_theme_dark, '#e4e4e4')

    def test_changing_a_dark_theme_color_customizes_only_the_dark_asset(self):
        settings = self.settings_model.create({})
        settings.color_appbar_active_theme_dark = '#654321'
        settings.execute()
        self.assertTrue(self._is_customized('theme_dark'))
        self.assertFalse(self._is_customized('theme_light'))
        self.assertEqual(
            self.settings_model.create({}).color_appbar_active_theme_dark,
            '#654321',
        )

    def test_theme_colors_are_independent_from_the_generic_colors(self):
        settings = self.settings_model.create({})
        settings.color_appbar_text_theme_light = '#334455'
        settings.execute()
        self.assertTrue(self._is_customized('theme_light'))
        self.assertFalse(self._is_customized('light'))
        self.assertEqual(self.settings_model.create({}).color_brand_light, '#243742')

    def test_reset_light_colors_also_resets_the_light_theme_asset(self):
        settings = self.settings_model.create({})
        settings.color_appbar_text_theme_light = '#123456'
        settings.color_brand_light = '#010203'
        settings.execute()
        self.assertTrue(self._is_customized('theme_light'))
        self.assertTrue(self._is_customized('light'))
        result = self.settings_model.create({}).action_reset_light_color_assets()
        self.assertEqual(result['tag'], 'reload')
        self.assertFalse(self._is_customized('theme_light'))
        self.assertFalse(self._is_customized('light'))

    def test_reset_dark_colors_keeps_the_light_theme_customization(self):
        settings = self.settings_model.create({})
        settings.color_appbar_text_theme_light = '#123456'
        settings.color_appbar_text_theme_dark = '#654321'
        settings.execute()
        result = self.settings_model.create({}).action_reset_dark_color_assets()
        self.assertEqual(result['tag'], 'reload')
        self.assertFalse(self._is_customized('theme_dark'))
        self.assertTrue(self._is_customized('theme_light'))

    def test_uninstall_cleanup_resets_both_theme_assets(self):
        settings = self.settings_model.create({})
        settings.color_appbar_text_theme_light = '#334455'
        settings.color_appbar_text_theme_dark = '#556677'
        settings.execute()
        self.assertTrue(self._is_customized('theme_light'))
        self.assertTrue(self._is_customized('theme_dark'))
        self.settings_model._reset_color_assets('theme_light')
        self.settings_model._reset_color_assets('theme_dark')
        self.assertFalse(self._is_customized('theme_light'))
        self.assertFalse(self._is_customized('theme_dark'))
