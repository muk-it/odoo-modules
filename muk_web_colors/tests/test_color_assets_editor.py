from __future__ import annotations

from odoo.tests import TransactionCase


class TestColorAssetsEditor(TransactionCase):
    """Test reading, writing and resetting the customized color assets."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        """Resolve the asset URLs and the values used by every test."""
        super().setUpClass()
        cls.editor = cls.env['muk_web_colors.color_assets_editor']
        cls.light_url = '/muk_web_colors/static/src/colors/light/light.scss'
        cls.light_bundle = 'web._assets_primary_variables'
        cls.light_custom_url = cls.editor._get_custom_colors_url(
            cls.light_url,
            cls.light_bundle,
        )
        cls.dark_url = '/muk_web_colors/static/src/colors/dark/dark.scss'
        cls.dark_bundle = 'web.assets_web_dark'
        cls.dark_custom_url = cls.editor._get_custom_colors_url(
            cls.dark_url,
            cls.dark_bundle,
        )
        cls.theme_url = '/muk_web_colors/static/src/colors/theme/theme.scss'
        cls.values = {'color_brand': '#112233', 'color_primary': '#445566'}

    def setUp(self) -> None:
        """Drop any customization left behind by another test."""
        super().setUp()
        self._cleanup_custom_asset(self.light_custom_url)
        self._cleanup_custom_asset(self.dark_custom_url)

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _cleanup_custom_asset(self, custom_url: str) -> None:
        """Remove any existing customized attachment and asset for a URL."""
        self.env['ir.attachment'].search([('url', '=', custom_url)]).unlink()
        self.env['ir.asset'].search([('path', '=', custom_url)]).unlink()

    def _bundle_paths(self, bundle: str) -> list[str]:
        """Return the asset paths a bundle resolves to, in load order."""
        assets = self.env['ir.asset']
        return [
            path
            for path, _full_path, _bundle, _modified in assets._get_asset_paths(
                bundle, assets._get_asset_params()
            )
        ]

    def _read_custom_content(self, custom_url: str) -> str:
        """Return the decoded content of the customized color attachment."""
        attachment = self.env['ir.attachment'].search([('url', '=', custom_url)])
        return attachment.raw.decode('utf-8')

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_write_creates_an_attachment_and_an_ir_asset(self):
        self.editor.write_colors(self.light_url, self.light_bundle, self.values)
        attachment = self.env['ir.attachment'].search(
            [('url', '=', self.light_custom_url)]
        )
        self.assertEqual(len(attachment), 1)
        self.assertEqual(attachment.mimetype, 'text/scss')
        asset = self.env['ir.asset'].search([('path', '=', self.light_custom_url)])
        self.assertEqual(len(asset), 1)
        self.assertEqual(asset.directive, 'replace')
        self.assertEqual(asset.target, self.light_url)
        self.assertTrue(asset.bundle)
        content = self._read_custom_content(self.light_custom_url)
        self.assertIn('$mk_color_brand: #112233;', content)
        self.assertIn('$mk_color_primary: #445566;', content)

    def test_write_twice_reuses_the_same_records(self):
        self.editor.write_colors(self.light_url, self.light_bundle, self.values)
        self.editor.write_colors(
            self.light_url,
            self.light_bundle,
            {'color_brand': '#AABBCC'},
        )
        attachment = self.env['ir.attachment'].search(
            [('url', '=', self.light_custom_url)]
        )
        asset = self.env['ir.asset'].search([('path', '=', self.light_custom_url)])
        self.assertEqual(len(attachment), 1)
        self.assertEqual(len(asset), 1)
        content = self._read_custom_content(self.light_custom_url)
        self.assertIn('$mk_color_brand: #AABBCC;', content)
        self.assertIn('$mk_color_primary: #445566;', content)

    def test_write_keeps_the_untouched_variables(self):
        defaults = self.editor.read_colors(
            self.light_url,
            self.light_bundle,
            ['color_success', 'color_danger'],
        )
        self.editor.write_colors(
            self.light_url,
            self.light_bundle,
            {'color_brand': '#010203'},
        )
        values = self.editor.read_colors(
            self.light_url,
            self.light_bundle,
            ['color_brand', 'color_success', 'color_danger'],
        )
        self.assertEqual(values['color_brand'], '#010203')
        self.assertEqual(values['color_success'], defaults['color_success'])
        self.assertEqual(values['color_danger'], defaults['color_danger'])

    def test_read_prefers_the_customized_attachment(self):
        self.editor.write_colors(self.light_url, self.light_bundle, self.values)
        values = self.editor.read_colors(
            self.light_url,
            self.light_bundle,
            ['color_brand', 'color_primary'],
        )
        self.assertEqual(values['color_brand'], '#112233')
        self.assertEqual(values['color_primary'], '#445566')

    def test_read_falls_back_to_the_module_file(self):
        values = self.editor.read_colors(
            self.light_url,
            self.light_bundle,
            ['color_brand', 'color_primary'],
        )
        self.assertEqual(values['color_brand'], '#243742')
        self.assertEqual(values['color_primary'], '#5d8da8')

    def test_read_returns_falsy_for_an_unknown_variable(self):
        values = self.editor.read_colors(
            self.light_url,
            self.light_bundle,
            ['color_brand', 'color_does_not_exist'],
        )
        self.assertEqual(values['color_brand'], '#243742')
        self.assertFalse(values['color_does_not_exist'])

    def test_the_light_and_dark_bundles_are_customized_independently(self):
        self.editor.write_colors(
            self.light_url,
            self.light_bundle,
            {'color_brand': '#101010'},
        )
        self.assertTrue(
            self.env['ir.attachment'].search([('url', '=', self.light_custom_url)])
        )
        self.assertFalse(
            self.env['ir.attachment'].search([('url', '=', self.dark_custom_url)])
        )
        dark = self.editor.read_colors(
            self.dark_url,
            self.dark_bundle,
            ['color_brand', 'color_success'],
        )
        self.assertEqual(dark['color_brand'], '#243742')
        self.assertEqual(dark['color_success'], '#1dc959')

    def test_reset_removes_the_attachment_and_the_ir_asset(self):
        self.editor.write_colors(self.light_url, self.light_bundle, self.values)
        self.editor.reset_colors(self.light_url, self.light_bundle)
        self.assertFalse(
            self.env['ir.attachment'].search([('url', '=', self.light_custom_url)])
        )
        self.assertFalse(
            self.env['ir.asset'].search([('path', '=', self.light_custom_url)])
        )

    def test_reset_without_a_customization_is_a_noop(self):
        self.editor.reset_colors(self.light_url, self.light_bundle)
        values = self.editor.read_colors(
            self.light_url,
            self.light_bundle,
            ['color_brand'],
        )
        self.assertEqual(values['color_brand'], '#243742')

    def test_the_dark_asset_overrides_the_light_one_in_the_dark_bundle(self):
        paths = self._bundle_paths(self.dark_bundle)
        light = paths.index(self.light_url)
        dark = paths.index(self.dark_url)
        theme = paths.index(self.theme_url)
        core = paths.index('/web/static/src/scss/primary_variables.scss')
        self.assertLess(light, dark)
        self.assertLess(dark, theme)
        self.assertLess(theme, core)

    def test_customizing_the_light_asset_keeps_the_dark_bundle_resolvable(self):
        self.editor.write_colors(self.light_url, self.light_bundle, self.values)
        paths = self._bundle_paths(self.dark_bundle)
        self.assertIn(self.light_custom_url, paths)
        self.assertNotIn(self.light_url, paths)
        self.assertLess(paths.index(self.light_custom_url), paths.index(self.dark_url))
