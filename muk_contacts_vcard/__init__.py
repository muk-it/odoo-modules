from __future__ import annotations

from odoo.api import Environment

from . import models


def _setup_module(env: Environment) -> None:
    """Split the name of the partners that have no name parts yet."""
    records = (
        env['res.partner']
        .with_context(active_test=False)
        .search(
            [
                ('firstname', '=', False),
                ('lastname', '=', False),
            ]
        )
    )
    records._inverse_name()
