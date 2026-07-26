from __future__ import annotations

from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestResConfigSettings(TransactionCase):
    """Cover the appsbar theme color settings round trip."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.settings_model = cls.env['res.config.settings']
        cls.editor = cls.env['muk_web_colors.color_assets_editor']
        cls.custom_urls = [
            cls.editor._get_custom_colors_url(url, bundle)
            for url, bundle in (
                (
                    '/muk_web_enterprise_theme/static/src/scss/colors_light.scss',
                    'web._assets_primary_variables',
                ),
                (
                    '/muk_web_enterprise_theme/static/src/scss/colors_dark.scss',
                    'web.assets_web_dark',
                ),
                (
                    '/muk_web_colors/static/src/scss/colors_light.scss',
                    'web._assets_primary_variables',
                ),
                (
                    '/muk_web_colors/static/src/scss/colors_dark.scss',
                    'web.assets_web_dark',
                ),
            )
        ]
        cls.theme_light_url, cls.theme_dark_url = cls.custom_urls[:2]

    def setUp(self) -> None:
        super().setUp()
        for custom_url in self.custom_urls:
            self.env['ir.attachment'].search([('url', '=', custom_url)]).unlink()
            self.env['ir.asset'].search([('path', '=', custom_url)]).unlink()

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _is_customized(self, custom_url: str) -> bool:
        """Return whether a customized color attachment exists for a URL."""
        return bool(self.env['ir.attachment'].search([('url', '=', custom_url)]))

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_settings_expose_the_theme_asset_defaults(self):
        settings = self.settings_model.create({})
        defaults = self.editor.get_color_variables_values(
            '/muk_web_enterprise_theme/static/src/scss/colors_light.scss',
            'web._assets_primary_variables',
            ['color_appbar_text', 'color_appbar_active', 'color_appbar_background'],
        )
        self.assertEqual(
            settings.theme_color_appbar_text_light,
            defaults['color_appbar_text'],
        )
        self.assertEqual(
            settings.theme_color_appbar_background_light,
            defaults['color_appbar_background'],
        )

    def test_saving_without_a_change_creates_no_customization(self):
        self.settings_model.create({}).execute()
        self.assertFalse(self._is_customized(self.theme_light_url))
        self.assertFalse(self._is_customized(self.theme_dark_url))

    def test_changing_a_light_theme_color_customizes_only_the_light_asset(self):
        settings = self.settings_model.create({})
        settings.theme_color_appbar_text_light = '#123456'
        settings.execute()
        self.assertTrue(self._is_customized(self.theme_light_url))
        self.assertFalse(self._is_customized(self.theme_dark_url))
        self.assertEqual(
            self.settings_model.create({}).theme_color_appbar_text_light,
            '#123456',
        )

    def test_changing_a_dark_theme_color_customizes_only_the_dark_asset(self):
        settings = self.settings_model.create({})
        settings.theme_color_appbar_active_dark = '#654321'
        settings.execute()
        self.assertTrue(self._is_customized(self.theme_dark_url))
        self.assertFalse(self._is_customized(self.theme_light_url))
        self.assertEqual(
            self.settings_model.create({}).theme_color_appbar_active_dark,
            '#654321',
        )

    def test_reset_light_colors_also_resets_the_theme_asset(self):
        settings = self.settings_model.create({})
        settings.theme_color_appbar_text_light = '#123456'
        settings.color_brand_light = '#010203'
        settings.execute()
        self.assertTrue(self._is_customized(self.theme_light_url))
        result = self.settings_model.create({}).action_reset_light_color_assets()
        self.assertEqual(result['tag'], 'reload')
        self.assertFalse(self._is_customized(self.theme_light_url))
        self.assertFalse(self._is_customized(self.custom_urls[2]))

    def test_reset_dark_colors_keeps_the_light_theme_customization(self):
        settings = self.settings_model.create({})
        settings.theme_color_appbar_text_light = '#123456'
        settings.theme_color_appbar_text_dark = '#654321'
        settings.execute()
        result = self.settings_model.create({}).action_reset_dark_color_assets()
        self.assertEqual(result['tag'], 'reload')
        self.assertFalse(self._is_customized(self.theme_dark_url))
        self.assertTrue(self._is_customized(self.theme_light_url))
