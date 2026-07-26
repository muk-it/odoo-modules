from __future__ import annotations

import base64

from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestColorAssetsEditor(TransactionCase):
    """Test reading, writing, and resetting customized color assets."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.editor = cls.env['muk_web_colors.color_assets_editor']
        cls.light_url = '/muk_web_colors/static/src/scss/colors_light.scss'
        cls.light_bundle = 'web._assets_primary_variables'
        cls.light_custom_url = cls.editor._get_custom_colors_url(
            cls.light_url,
            cls.light_bundle,
        )
        cls.dark_url = '/muk_web_colors/static/src/scss/colors_dark.scss'
        cls.dark_bundle = 'web.assets_web_dark'
        cls.dark_custom_url = cls.editor._get_custom_colors_url(
            cls.dark_url,
            cls.dark_bundle,
        )
        cls.variables = [
            {'name': 'color_brand', 'value': '#112233'},
            {'name': 'color_primary', 'value': '#445566'},
        ]

    def setUp(self) -> None:
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

    def _read_custom_content(self, custom_url: str) -> str:
        """Return the decoded content of the customized color attachment."""
        attachment = self.env['ir.attachment'].search([('url', '=', custom_url)])
        raw = attachment.datas or b''
        if isinstance(raw, str):
            raw = raw.encode('ascii')
        return base64.b64decode(raw).decode('utf-8')

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_replace_creates_ir_asset_and_attachment(self):
        self.editor.replace_color_variables_values(
            self.light_url,
            self.light_bundle,
            self.variables,
        )
        attachment = self.env['ir.attachment'].search(
            [('url', '=', self.light_custom_url)]
        )
        self.assertEqual(len(attachment), 1)
        asset = self.env['ir.asset'].search([('path', '=', self.light_custom_url)])
        self.assertEqual(len(asset), 1)
        self.assertEqual(asset.directive, 'replace')
        self.assertEqual(asset.target, self.light_url)
        self.assertTrue(asset.bundle)
        content = self._read_custom_content(self.light_custom_url)
        self.assertIn('color_brand: #112233;', content)
        self.assertIn('color_primary: #445566;', content)

    def test_replace_twice_reuses_the_same_records(self):
        self.editor.replace_color_variables_values(
            self.light_url,
            self.light_bundle,
            self.variables,
        )
        self.editor.replace_color_variables_values(
            self.light_url,
            self.light_bundle,
            [{'name': 'color_brand', 'value': '#AABBCC'}],
        )
        attachment = self.env['ir.attachment'].search(
            [('url', '=', self.light_custom_url)]
        )
        asset = self.env['ir.asset'].search([('path', '=', self.light_custom_url)])
        self.assertEqual(len(attachment), 1)
        self.assertEqual(len(asset), 1)
        content = self._read_custom_content(self.light_custom_url)
        self.assertIn('color_brand: #AABBCC;', content)
        self.assertIn('color_primary: #445566;', content)

    def test_replace_keeps_untouched_variables(self):
        defaults = self.editor.get_color_variables_values(
            self.light_url,
            self.light_bundle,
            ['color_success', 'color_danger'],
        )
        self.editor.replace_color_variables_values(
            self.light_url,
            self.light_bundle,
            [{'name': 'color_brand', 'value': '#010203'}],
        )
        values = self.editor.get_color_variables_values(
            self.light_url,
            self.light_bundle,
            ['color_brand', 'color_success', 'color_danger'],
        )
        self.assertEqual(values['color_brand'], '#010203')
        self.assertEqual(values['color_success'], defaults['color_success'])
        self.assertEqual(values['color_danger'], defaults['color_danger'])

    def test_get_values_reads_customized_file(self):
        self.editor.replace_color_variables_values(
            self.light_url,
            self.light_bundle,
            self.variables,
        )
        values = self.editor.get_color_variables_values(
            self.light_url,
            self.light_bundle,
            ['color_brand', 'color_primary'],
        )
        self.assertEqual(values['color_brand'], '#112233')
        self.assertEqual(values['color_primary'], '#445566')

    def test_get_values_falls_back_to_the_module_file(self):
        values = self.editor.get_color_variables_values(
            self.light_url,
            self.light_bundle,
            ['color_brand', 'color_primary'],
        )
        self.assertEqual(values['color_brand'], '#243742')
        self.assertEqual(values['color_primary'], '#5D8DA8')

    def test_get_values_returns_falsy_for_an_unknown_variable(self):
        values = self.editor.get_color_variables_values(
            self.light_url,
            self.light_bundle,
            ['color_brand', 'color_does_not_exist'],
        )
        self.assertEqual(values['color_brand'], '#243742')
        self.assertFalse(values['color_does_not_exist'])

    def test_light_and_dark_bundles_are_customized_independently(self):
        self.editor.replace_color_variables_values(
            self.light_url,
            self.light_bundle,
            [{'name': 'color_brand', 'value': '#101010'}],
        )
        self.assertTrue(
            self.env['ir.attachment'].search([('url', '=', self.light_custom_url)])
        )
        self.assertFalse(
            self.env['ir.attachment'].search([('url', '=', self.dark_custom_url)])
        )
        dark = self.editor.get_color_variables_values(
            self.dark_url,
            self.dark_bundle,
            ['color_brand', 'color_success'],
        )
        self.assertEqual(dark['color_brand'], '#243742')
        self.assertEqual(dark['color_success'], '#1DC959')

    def test_reset_removes_ir_asset_and_attachment(self):
        self.editor.replace_color_variables_values(
            self.light_url,
            self.light_bundle,
            self.variables,
        )
        self.editor.reset_color_asset(self.light_url, self.light_bundle)
        self.assertFalse(
            self.env['ir.attachment'].search([('url', '=', self.light_custom_url)])
        )
        self.assertFalse(
            self.env['ir.asset'].search([('path', '=', self.light_custom_url)])
        )

    def test_reset_without_customization_is_a_noop(self):
        self.editor.reset_color_asset(self.light_url, self.light_bundle)
        values = self.editor.get_color_variables_values(
            self.light_url,
            self.light_bundle,
            ['color_brand'],
        )
        self.assertEqual(values['color_brand'], '#243742')

    def test_url_info_of_a_customized_url(self):
        info = self.editor._get_color_info_from_url(self.light_custom_url)
        self.assertTrue(info['customized'])
        self.assertEqual(info['bundle'], self.light_bundle)
        self.assertEqual(info['module'], 'muk_web_colors')
        self.assertEqual(info['resource_path'], 'static/src/scss/colors_light.scss')

    def test_url_info_of_a_plain_module_url(self):
        info = self.editor._get_color_info_from_url(self.light_url)
        self.assertFalse(info['customized'])
        self.assertFalse(info['bundle'])
        self.assertEqual(info['module'], 'muk_web_colors')

    def test_url_info_of_a_malformed_url(self):
        self.assertFalse(self.editor._get_color_info_from_url('not-a-url'))
        self.assertFalse(self.editor._get_color_info_from_url('/no-extension'))
