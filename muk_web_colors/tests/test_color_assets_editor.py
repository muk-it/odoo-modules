from odoo.addons.muk_web_colors.tests.common import ColorsCase


class TestColorAssetsEditor(ColorsCase):
    """Test reading, writing and resetting the customized color assets."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        """Resolve the light and dark color assets."""
        super().setUpClass()
        cls.light_url, cls.light_bundle, cls.names = cls.settings_model.COLOR_ASSETS[
            'light'
        ]
        cls.dark_url, cls.dark_bundle, _names = cls.settings_model.COLOR_ASSETS['dark']

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_read_falls_back_to_the_module_file(self):
        values = self.editor.read_colors(
            self.light_url, self.light_bundle, ['color_brand', 'color_unknown']
        )
        self.assertEqual(values, {'color_brand': '#243742', 'color_unknown': False})

    def test_writes_update_one_customization_and_keep_other_colors(self):
        defaults = self.editor.read_colors(
            self.light_url, self.light_bundle, self.names
        )
        dark = self.editor.read_colors(self.dark_url, self.dark_bundle, self.names)
        self.editor.write_colors(
            self.light_url,
            self.light_bundle,
            {'color_brand': '#112233', 'color_primary': '#445566'},
        )
        self.editor.write_colors(
            self.light_url, self.light_bundle, {'color_brand': '#AABBCC'}
        )
        self.assertEqual(self._customization('light'), (1, 1))
        self.assertEqual(self._customization('dark'), (0, 0))
        self.assertEqual(
            self.editor.read_colors(self.light_url, self.light_bundle, self.names),
            {**defaults, 'color_brand': '#AABBCC', 'color_primary': '#445566'},
        )
        self.assertEqual(
            self.editor.read_colors(self.dark_url, self.dark_bundle, self.names), dark
        )

    def test_reset_restores_the_module_file(self):
        self.editor.reset_colors(self.light_url, self.light_bundle)
        self.editor.write_colors(
            self.light_url, self.light_bundle, {'color_brand': '#112233'}
        )
        self.editor.reset_colors(self.light_url, self.light_bundle)
        self.assertEqual(self._customization('light'), (0, 0))
        values = self.editor.read_colors(
            self.light_url, self.light_bundle, ['color_brand']
        )
        self.assertEqual(values, {'color_brand': '#243742'})

    def test_the_dark_asset_overrides_the_light_one_in_the_dark_bundle(self):
        paths = self._bundle_paths(self.dark_bundle)
        order = [
            self.light_url,
            self.dark_url,
            '/muk_web_colors/static/src/colors/theme/theme.scss',
            '/web/static/src/scss/primary_variables.scss',
        ]
        indexes = [paths.index(path) for path in order]
        self.assertEqual(indexes, sorted(indexes))

    def test_the_customized_light_asset_replaces_it_in_both_bundles(self):
        self.editor.write_colors(
            self.light_url, self.light_bundle, {'color_brand': '#112233'}
        )
        custom_url = self.editor._get_custom_colors_url(
            self.light_url, self.light_bundle
        )
        for bundle in (self.light_bundle, self.dark_bundle):
            with self.subTest(bundle=bundle):
                paths = self._bundle_paths(bundle)
                self.assertIn(custom_url, paths)
                self.assertNotIn(self.light_url, paths)
        self.assertLess(paths.index(custom_url), paths.index(self.dark_url))
