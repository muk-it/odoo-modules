from __future__ import annotations

from odoo.tests import TransactionCase

from odoo.addons.muk_web_enterprise_theme import _uninstall_cleanup


class TestResConfigSettings(TransactionCase):
    """Cover saving and resetting the appsbar theme color palettes."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        """Map the customized asset URL of every color palette to its name."""
        super().setUpClass()
        cls.settings_model = cls.env['res.config.settings']
        editor = cls.env['muk_web_colors.color_assets_editor']
        cls.palettes = {
            editor._get_custom_colors_url(url, bundle): palette
            for palette, (
                url,
                bundle,
                _names,
            ) in cls.settings_model.COLOR_ASSETS.items()
        }

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _save(self, values: dict[str, str]) -> None:
        """Save the given colors through the settings form."""
        self.settings_model.create(values).execute()

    def _customized(self) -> set[str]:
        """Return the palettes that have a customized color asset."""
        attachments = self.env['ir.attachment'].search(
            [('url', 'in', list(self.palettes))]
        )
        return {self.palettes[url] for url in attachments.mapped('url')}

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_saving_a_theme_color_customizes_only_its_palette(self):
        self._save({'color_appbar_text_theme_light': '#123456'})
        self.assertEqual(self._customized(), {'theme_light'})
        self._save({'color_appbar_active_theme_dark': '#654321'})
        self.assertEqual(self._customized(), {'theme_light', 'theme_dark'})
        settings = self.settings_model.create({})
        self.assertEqual(settings.color_appbar_text_theme_light, '#123456')
        self.assertEqual(settings.color_appbar_active_theme_dark, '#654321')

    def test_reset_clears_the_theme_palette_of_its_scheme_only(self):
        for scheme, other in (('light', 'dark'), ('dark', 'light')):
            with self.subTest(scheme=scheme):
                self._save(
                    {
                        'color_brand_light': '#010203',
                        'color_brand_dark': '#030201',
                        'color_appbar_text_theme_light': '#123456',
                        'color_appbar_text_theme_dark': '#654321',
                    }
                )
                action = f'action_reset_{scheme}_color_assets'
                result = getattr(self.settings_model.create({}), action)()
                self.assertEqual(result['tag'], 'reload')
                self.assertEqual(self._customized(), {other, f'theme_{other}'})

    def test_uninstall_resets_both_theme_palettes(self):
        self._save(
            {
                'color_brand_light': '#010203',
                'color_appbar_text_theme_light': '#334455',
                'color_appbar_text_theme_dark': '#556677',
            }
        )
        _uninstall_cleanup(self.env)
        self.assertEqual(self._customized(), {'light'})
