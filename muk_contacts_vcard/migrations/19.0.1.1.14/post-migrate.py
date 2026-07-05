from __future__ import annotations

from odoo import SUPERUSER_ID, api
from odoo.sql_db import Cursor


def migrate(cr: Cursor, version: str) -> None:
    """Split the names of archived partners skipped by the install hook."""
    env = api.Environment(cr, SUPERUSER_ID, {})
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
