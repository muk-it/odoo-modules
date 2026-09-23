from __future__ import annotations

from odoo.api import Environment
from odoo.tools import BinaryBytes, file_open

from . import models


def _setup_module(env: Environment) -> None:
    """Seed the main company favicon from Odoo's default favicon image."""
    company = env.ref('base.main_company', False)
    if not company:
        return
    with file_open('web/static/img/favicon.ico', 'rb') as file:
        company.favicon = BinaryBytes(file.read(), filename='favicon.ico')


def _uninstall_cleanup(env: Environment) -> None:
    """Reset the light and dark appsbar color assets on module uninstall."""
    env['res.config.settings']._reset_color_assets('theme_light')
    env['res.config.settings']._reset_color_assets('theme_dark')
