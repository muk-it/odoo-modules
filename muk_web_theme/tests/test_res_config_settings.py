from __future__ import annotations

from odoo.tests import TransactionCase


class TestResConfigSettings(TransactionCase):
    """Cover the backend theme color settings round trip."""

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

    def test_the_theme_palette_is_registered(self):
        self.assertIn('theme', self.settings_model.COLOR_ASSETS)
        url, bundle, names = self.settings_model.COLOR_ASSETS['theme']
        self.assertEqual(url, '/muk_web_theme/static/src/colors/theme/theme.scss')
        self.assertEqual(bundle, 'web._assets_primary_variables')
        self.assertEqual(
            names,
            (
                'color_appsmenu_text',
                'color_appbar_text',
                'color_appbar_active',
                'color_appbar_background',
            ),
        )

    def test_settings_expose_the_theme_asset_defaults(self):
        settings = self.settings_model.create({})
        self.assertEqual(settings.color_appsmenu_text_theme, '#f8f9fa')
        self.assertEqual(settings.color_appbar_text_theme, '#dee2e6')
        self.assertEqual(settings.color_appbar_active_theme, '#5d8da8')
        self.assertEqual(settings.color_appbar_background_theme, '#111827')

    def test_saving_without_a_change_creates_no_customization(self):
        self.settings_model.create({}).execute()
        self.assertFalse(self._is_customized('theme'))

    def test_changing_a_theme_color_customizes_the_theme_asset(self):
        settings = self.settings_model.create({})
        settings.color_appbar_background_theme = '#001122'
        settings.execute()
        self.assertTrue(self._is_customized('theme'))
        reloaded = self.settings_model.create({})
        self.assertEqual(reloaded.color_appbar_background_theme, '#001122')
        self.assertEqual(reloaded.color_appbar_text_theme, '#dee2e6')

    def test_theme_colors_are_independent_from_the_generic_colors(self):
        settings = self.settings_model.create({})
        settings.color_appbar_text_theme = '#334455'
        settings.execute()
        self.assertTrue(self._is_customized('theme'))
        self.assertFalse(self._is_customized('light'))
        self.assertEqual(
            self.settings_model.create({}).color_brand_light,
            '#243742',
        )

    def test_reset_theme_colors_resets_every_color_asset(self):
        settings = self.settings_model.create({})
        settings.color_appbar_text_theme = '#334455'
        settings.color_brand_light = '#010203'
        settings.color_brand_dark = '#040506'
        settings.execute()
        for palette in self.custom_urls:
            self.assertTrue(self._is_customized(palette))
        result = self.settings_model.create({}).action_reset_theme_color_assets()
        self.assertEqual(result['tag'], 'reload')
        for palette in self.custom_urls:
            self.assertFalse(self._is_customized(palette))

    def test_uninstall_cleanup_resets_the_theme_asset(self):
        settings = self.settings_model.create({})
        settings.color_appbar_text_theme = '#334455'
        settings.execute()
        self.assertTrue(self._is_customized('theme'))
        self.settings_model._reset_color_assets('theme')
        self.assertFalse(self._is_customized('theme'))
