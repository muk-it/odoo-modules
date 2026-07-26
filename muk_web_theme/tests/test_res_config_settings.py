from __future__ import annotations

from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestResConfigSettings(TransactionCase):
    """Cover the backend theme color settings round trip."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.settings_model = cls.env['res.config.settings']
        cls.editor = cls.env['muk_web_colors.color_assets_editor']
        cls.theme_url = '/muk_web_theme/static/src/scss/colors.scss'
        cls.theme_bundle = 'web._assets_primary_variables'
        cls.theme_custom_url = cls.editor._get_custom_colors_url(
            cls.theme_url,
            cls.theme_bundle,
        )
        cls.light_custom_url = cls.editor._get_custom_colors_url(
            '/muk_web_colors/static/src/scss/colors_light.scss',
            'web._assets_primary_variables',
        )
        cls.dark_custom_url = cls.editor._get_custom_colors_url(
            '/muk_web_colors/static/src/scss/colors_dark.scss',
            'web.assets_web_dark',
        )

    def setUp(self) -> None:
        super().setUp()
        for custom_url in (
            self.theme_custom_url,
            self.light_custom_url,
            self.dark_custom_url,
        ):
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
        self.assertEqual(settings.theme_color_appsmenu_text, '#F8F9FA')
        self.assertEqual(settings.theme_color_appbar_text, '#DEE2E6')
        self.assertEqual(settings.theme_color_appbar_active, '#5D8DA8')
        self.assertEqual(settings.theme_color_appbar_background, '#111827')

    def test_saving_without_a_change_creates_no_customization(self):
        self.settings_model.create({}).execute()
        self.assertFalse(self._is_customized(self.theme_custom_url))

    def test_changing_a_theme_color_customizes_the_theme_asset(self):
        settings = self.settings_model.create({})
        settings.theme_color_appbar_background = '#001122'
        settings.execute()
        self.assertTrue(self._is_customized(self.theme_custom_url))
        reloaded = self.settings_model.create({})
        self.assertEqual(reloaded.theme_color_appbar_background, '#001122')
        self.assertEqual(reloaded.theme_color_appbar_text, '#DEE2E6')

    def test_theme_colors_are_independent_from_the_generic_colors(self):
        settings = self.settings_model.create({})
        settings.theme_color_appbar_text = '#334455'
        settings.execute()
        self.assertTrue(self._is_customized(self.theme_custom_url))
        self.assertFalse(self._is_customized(self.light_custom_url))
        self.assertEqual(
            self.settings_model.create({}).color_brand_light,
            '#243742',
        )

    def test_reset_theme_colors_resets_every_color_asset(self):
        settings = self.settings_model.create({})
        settings.theme_color_appbar_text = '#334455'
        settings.color_brand_light = '#010203'
        settings.color_brand_dark = '#040506'
        settings.execute()
        self.assertTrue(self._is_customized(self.theme_custom_url))
        self.assertTrue(self._is_customized(self.light_custom_url))
        self.assertTrue(self._is_customized(self.dark_custom_url))
        result = self.settings_model.create({}).action_reset_theme_color_assets()
        self.assertEqual(result['tag'], 'reload')
        self.assertFalse(self._is_customized(self.theme_custom_url))
        self.assertFalse(self._is_customized(self.light_custom_url))
        self.assertFalse(self._is_customized(self.dark_custom_url))

    def test_uninstall_cleanup_resets_the_theme_asset(self):
        settings = self.settings_model.create({})
        settings.theme_color_appbar_text = '#334455'
        settings.execute()
        self.assertTrue(self._is_customized(self.theme_custom_url))
        self.settings_model._reset_theme_color_assets()
        self.assertFalse(self._is_customized(self.theme_custom_url))
