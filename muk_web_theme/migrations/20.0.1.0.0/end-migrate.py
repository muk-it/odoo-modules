from __future__ import annotations

from odoo import SUPERUSER_ID, api
from odoo.sql_db import Cursor

from odoo.addons.muk_web_colors.tools import read_variables

OLD_URL = '/muk_web_theme/static/src/scss/colors.scss'


def migrate(cr: Cursor, version: str | None) -> None:
    """Move the customized colors of the 19.0 theme asset to the 20.0 asset."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    editor = env['muk_web_colors.color_assets_editor']
    url, bundle, names = env['res.config.settings'].COLOR_ASSETS['theme']
    custom_url = editor._get_custom_colors_url(OLD_URL, bundle)
    attachment = editor._get_colors_attachment(custom_url)
    if attachment:
        values = read_variables(attachment.raw.decode('utf-8'), names)
        attachment.unlink()
        env['ir.asset'].search([('path', '=', custom_url)]).unlink()
        editor.write_colors(url, bundle, {k: v for k, v in values.items() if v})
