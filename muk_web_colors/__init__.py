from __future__ import annotations

from odoo.api import Environment

from . import models


def _uninstall_cleanup(env: Environment) -> None:
    """Reset the customized light and dark color assets on uninstall."""
    env['res.config.settings']._reset_color_assets('light')
    env['res.config.settings']._reset_color_assets('dark')
