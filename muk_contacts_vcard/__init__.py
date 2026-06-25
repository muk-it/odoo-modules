from __future__ import annotations

from odoo.api import Environment

from . import models


def _setup_module(env: Environment) -> None:
    """Split unnamed partners into first/last name on install."""
    records = env['res.partner'].search(
        [
            ('firstname', '=', False),
            ('lastname', '=', False),
        ]
    )
    records._inverse_name()
