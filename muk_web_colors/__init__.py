from . import models

from odoo import api, SUPERUSER_ID


def _uninstall_cleanup(env):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['res.config.settings']._reset_light_color_assets()
    env['res.config.settings']._reset_dark_color_assets()