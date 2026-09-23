from __future__ import annotations

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    """Manage the backend theme favicon, background images, and colors."""

    _inherit = 'res.config.settings'

    # ----------------------------------------------------------
    # Properties
    # ----------------------------------------------------------

    @property
    def COLOR_ASSETS(self) -> dict[str, tuple[str, str, tuple[str, ...]]]:
        """Add the light and dark appsbar palettes to the color assets."""
        names = (
            'color_appbar_text',
            'color_appbar_active',
            'color_appbar_background',
        )
        return {
            **super().COLOR_ASSETS,
            'theme_light': (
                '/muk_web_enterprise_theme/static/src/colors/light/light.scss',
                'web._assets_primary_variables',
                names,
            ),
            'theme_dark': (
                '/muk_web_enterprise_theme/static/src/colors/dark/dark.scss',
                'web.assets_web_dark',
                names,
            ),
        }

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    theme_favicon = fields.Binary(
        related='company_id.favicon',
        readonly=False,
    )

    theme_background_image_light = fields.Binary(
        related='company_id.background_image_light',
        readonly=False,
    )

    theme_background_image_dark = fields.Binary(
        related='company_id.background_image_dark',
        readonly=False,
    )

    color_appbar_text_theme_light = fields.Char(
        string='AppsBar Text Light Color',
    )

    color_appbar_active_theme_light = fields.Char(
        string='AppsBar Active Light Color',
    )

    color_appbar_background_theme_light = fields.Char(
        string='AppsBar Background Light Color',
    )

    color_appbar_text_theme_dark = fields.Char(
        string='AppsBar Text Dark Color',
    )

    color_appbar_active_theme_dark = fields.Char(
        string='AppsBar Active Dark Color',
    )

    color_appbar_background_theme_dark = fields.Char(
        string='AppsBar Background Dark Color',
    )

    # ----------------------------------------------------------
    # Actions
    # ----------------------------------------------------------

    def action_reset_light_color_assets(self) -> dict:
        """Reset the light appsbar palette before the standard reset."""
        self._reset_color_assets('theme_light')
        return super().action_reset_light_color_assets()

    def action_reset_dark_color_assets(self) -> dict:
        """Reset the dark appsbar palette before the standard reset."""
        self._reset_color_assets('theme_dark')
        return super().action_reset_dark_color_assets()
