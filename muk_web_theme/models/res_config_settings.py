from __future__ import annotations

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    """Manage the backend theme favicon, background image, and colors."""

    _inherit = 'res.config.settings'

    # ----------------------------------------------------------
    # Properties
    # ----------------------------------------------------------

    @property
    def COLOR_ASSETS(self) -> dict[str, tuple[str, str, tuple[str, ...]]]:
        """Add the backend theme palette to the customizable color assets."""
        return {
            **super().COLOR_ASSETS,
            'theme': (
                '/muk_web_theme/static/src/colors/theme/theme.scss',
                'web._assets_primary_variables',
                (
                    'color_appsmenu_text',
                    'color_appbar_text',
                    'color_appbar_active',
                    'color_appbar_background',
                ),
            ),
        }

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    theme_favicon = fields.Binary(
        related='company_id.favicon',
        readonly=False,
    )

    theme_background_image = fields.Binary(
        related='company_id.background_image',
        readonly=False,
    )

    color_appsmenu_text_theme = fields.Char(
        string='Apps Menu Text Color',
    )

    color_appbar_text_theme = fields.Char(
        string='AppsBar Text Color',
    )

    color_appbar_active_theme = fields.Char(
        string='AppsBar Active Color',
    )

    color_appbar_background_theme = fields.Char(
        string='AppsBar Background Color',
    )

    # ----------------------------------------------------------
    # Actions
    # ----------------------------------------------------------

    def action_reset_theme_color_assets(self) -> dict:
        """Reset every color palette and reload the client."""
        for palette in self.COLOR_ASSETS:
            self._reset_color_assets(palette)
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }
