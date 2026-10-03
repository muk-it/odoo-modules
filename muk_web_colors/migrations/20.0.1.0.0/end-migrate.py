from __future__ import annotations

from odoo import SUPERUSER_ID, api
from odoo.sql_db import Cursor

from odoo.addons.muk_web_colors.tools import read_variables

PALETTES = {
    'light': '/muk_web_colors/static/src/scss/colors_light.scss',
    'dark': '/muk_web_colors/static/src/scss/colors_dark.scss',
}


def migrate(cr: Cursor, version: str | None) -> None:
    """Move the customized colors of the 19.0 color assets to the 20.0 assets."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    editor = env['muk_web_colors.color_assets_editor']
    for palette, old_url in PALETTES.items():
        url, bundle, names = env['res.config.settings'].COLOR_ASSETS[palette]
        custom_url = editor._get_custom_colors_url(old_url, bundle)
        attachment = editor._get_colors_attachment(custom_url)
        if not attachment:
            continue
        values = read_variables(attachment.raw.decode('utf-8'), names)
        attachment.unlink()
        env['ir.asset'].search([('path', '=', custom_url)]).unlink()
        editor.write_colors(url, bundle, {k: v for k, v in values.items() if v})
