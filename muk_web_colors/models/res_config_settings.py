from __future__ import annotations

from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    """Expose the theme color variables as light and dark settings fields."""

    _inherit = 'res.config.settings'

    # ----------------------------------------------------------
    # Properties
    # ----------------------------------------------------------

    @property
    def COLOR_FIELDS(self) -> tuple[str, ...]:
        """Return the names of the customizable color variables."""
        return (
            'color_brand',
            'color_primary',
            'color_success',
            'color_info',
            'color_warning',
            'color_danger',
        )

    @property
    def COLOR_ASSETS(self) -> dict[str, tuple[str, str]]:
        """Return the asset URL and the bundle name of every color mode."""
        return {
            'light': (
                '/muk_web_colors/static/src/colors/light/light.scss',
                'web._assets_primary_variables',
            ),
            'dark': (
                '/muk_web_colors/static/src/colors/dark/dark.scss',
                'web.assets_web_dark',
            ),
        }

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    color_brand_light = fields.Char(
        string='Brand Light Color',
    )

    color_primary_light = fields.Char(
        string='Primary Light Color',
    )

    color_success_light = fields.Char(
        string='Success Light Color',
    )

    color_info_light = fields.Char(
        string='Info Light Color',
    )

    color_warning_light = fields.Char(
        string='Warning Light Color',
    )

    color_danger_light = fields.Char(
        string='Danger Light Color',
    )

    color_brand_dark = fields.Char(
        string='Brand Dark Color',
    )

    color_primary_dark = fields.Char(
        string='Primary Dark Color',
    )

    color_success_dark = fields.Char(
        string='Success Dark Color',
    )

    color_info_dark = fields.Char(
        string='Info Dark Color',
    )

    color_warning_dark = fields.Char(
        string='Warning Dark Color',
    )

    color_danger_dark = fields.Char(
        string='Danger Dark Color',
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _get_color_values(self, mode: str) -> dict:
        """Return the color values stored in the asset of one color mode."""
        url, bundle = self.COLOR_ASSETS[mode]
        return self.env['muk_web_colors.color_assets_editor'].read_colors(
            url, bundle, self.COLOR_FIELDS
        )

    def _detect_color_change(self, mode: str) -> bool:
        """Return whether a color field of one mode differs from its asset."""
        stored = self._get_color_values(mode)
        return any(self[f'{name}_{mode}'] != value for name, value in stored.items())

    def _replace_color_values(self, mode: str) -> None:
        """Save the color fields of one mode to its customized asset."""
        url, bundle = self.COLOR_ASSETS[mode]
        values = {name: self[f'{name}_{mode}'] for name in self.COLOR_FIELDS}
        self.env['muk_web_colors.color_assets_editor'].write_colors(url, bundle, values)

    @api.model
    def _reset_color_assets(self, mode: str) -> None:
        """Delete the customized color asset of one color mode."""
        url, bundle = self.COLOR_ASSETS[mode]
        self.env['muk_web_colors.color_assets_editor'].reset_colors(url, bundle)

    # ----------------------------------------------------------
    # Actions
    # ----------------------------------------------------------

    def action_reset_light_color_assets(self) -> dict:
        """Reset the light mode colors and reload the client."""
        self._reset_color_assets('light')
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }

    def action_reset_dark_color_assets(self) -> dict:
        """Reset the dark mode colors and reload the client."""
        self._reset_color_assets('dark')
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    def get_values(self) -> dict:
        """Add the stored light and dark color values to the settings values."""
        values = super().get_values()
        for mode in self.COLOR_ASSETS:
            for name, value in self._get_color_values(mode).items():
                values[f'{name}_{mode}'] = value
        return values

    def set_values(self) -> None:
        """Save the changed light and dark color values to their assets."""
        super().set_values()
        for mode in self.COLOR_ASSETS:
            if self._detect_color_change(mode):
                self._replace_color_values(mode)
