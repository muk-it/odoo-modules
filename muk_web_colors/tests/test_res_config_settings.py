from __future__ import annotations

from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestResConfigSettings(TransactionCase):
    """Cover the light and dark color settings round trip."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.settings_model = cls.env['res.config.settings']
        cls.editor = cls.env['muk_web_colors.color_assets_editor']
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
        for custom_url in (self.light_custom_url, self.dark_custom_url):
            self.env['ir.attachment'].search([('url', '=', custom_url)]).unlink()
            self.env['ir.asset'].search([('path', '=', custom_url)]).unlink()

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _custom_attachment(self, custom_url: str) -> object:
        """Return the customized color attachment for a bundle URL."""
        return self.env['ir.attachment'].search([('url', '=', custom_url)])

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_settings_expose_the_asset_defaults(self):
        settings = self.settings_model.create({})
        self.assertEqual(settings.color_brand_light, '#243742')
        self.assertEqual(settings.color_primary_light, '#5D8DA8')
        self.assertEqual(settings.color_success_light, '#28A745')
        self.assertEqual(settings.color_success_dark, '#1DC959')
        self.assertEqual(settings.color_danger_dark, '#FF5757')

    def test_saving_without_a_change_creates_no_customization(self):
        self.settings_model.create({}).execute()
        self.assertFalse(self._custom_attachment(self.light_custom_url))
        self.assertFalse(self._custom_attachment(self.dark_custom_url))

    def test_changing_a_light_color_customizes_only_the_light_asset(self):
        settings = self.settings_model.create({})
        settings.color_brand_light = '#0A0B0C'
        settings.execute()
        self.assertTrue(self._custom_attachment(self.light_custom_url))
        self.assertFalse(self._custom_attachment(self.dark_custom_url))
        self.assertEqual(
            self.settings_model.create({}).color_brand_light,
            '#0A0B0C',
        )

    def test_changing_a_dark_color_customizes_only_the_dark_asset(self):
        settings = self.settings_model.create({})
        settings.color_warning_dark = '#0D0E0F'
        settings.execute()
        self.assertTrue(self._custom_attachment(self.dark_custom_url))
        self.assertFalse(self._custom_attachment(self.light_custom_url))
        reloaded = self.settings_model.create({})
        self.assertEqual(reloaded.color_warning_dark, '#0D0E0F')
        self.assertEqual(reloaded.color_warning_light, '#FFAC00')

    def test_reset_light_colors_drops_the_customization(self):
        settings = self.settings_model.create({})
        settings.color_brand_light = '#0A0B0C'
        settings.execute()
        result = self.settings_model.create({}).action_reset_light_color_assets()
        self.assertEqual(result['tag'], 'reload')
        self.assertFalse(self._custom_attachment(self.light_custom_url))
        self.assertEqual(
            self.settings_model.create({}).color_brand_light,
            '#243742',
        )

    def test_reset_dark_colors_keeps_the_light_customization(self):
        settings = self.settings_model.create({})
        settings.color_brand_light = '#0A0B0C'
        settings.color_brand_dark = '#0D0E0F'
        settings.execute()
        result = self.settings_model.create({}).action_reset_dark_color_assets()
        self.assertEqual(result['tag'], 'reload')
        self.assertFalse(self._custom_attachment(self.dark_custom_url))
        self.assertTrue(self._custom_attachment(self.light_custom_url))
        self.assertEqual(
            self.settings_model.create({}).color_brand_light,
            '#0A0B0C',
        )
