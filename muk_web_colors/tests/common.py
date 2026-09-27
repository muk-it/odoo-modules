from __future__ import annotations

from odoo.tests import TransactionCase


class ColorsCase(TransactionCase):
    """Start every test from the uncustomized color assets."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        """Reset every color palette and resolve the shared models."""
        super().setUpClass()
        cls.settings_model = cls.env['res.config.settings']
        cls.editor = cls.env['muk_web_colors.color_assets_editor']
        for palette in cls.settings_model.COLOR_ASSETS:
            cls.settings_model._reset_color_assets(palette)

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _customization(self, palette: str) -> tuple[int, int]:
        """Return how many attachments and ``ir.asset`` customize a palette."""
        url, bundle, _names = self.settings_model.COLOR_ASSETS[palette]
        custom_url = self.editor._get_custom_colors_url(url, bundle)
        return (
            self.env['ir.attachment'].search_count([('url', '=', custom_url)]),
            self.env['ir.asset'].search_count([('path', '=', custom_url)]),
        )

    def _bundle_paths(self, bundle: str) -> list[str]:
        """Return the asset paths a bundle resolves to, in load order."""
        assets = self.env['ir.asset']
        params = assets._get_asset_params()
        return [path for path, *_rest in assets._get_asset_paths(bundle, params)]
