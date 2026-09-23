from __future__ import annotations

from odoo.api import Environment
from odoo.tools import BinaryBytes, file_open

from . import models


def _setup_module(env: Environment) -> None:
    """Seed the main company favicon and apps-menu background image."""
    company = env.ref('base.main_company', False)
    if not company:
        return
    with file_open('web/static/img/favicon.ico', 'rb') as file:
        company.favicon = BinaryBytes(file.read(), filename='favicon.ico')
    with file_open(
        'muk_web_theme/static/src/webclient/appsmenu/background.png', 'rb'
    ) as file:
        company.background_image = BinaryBytes(file.read(), filename='background.png')


def _uninstall_cleanup(env: Environment) -> None:
    """Reset the theme color asset on module uninstall."""
    env['res.config.settings']._reset_color_assets('theme')
