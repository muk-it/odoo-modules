from __future__ import annotations

from odoo.sql_db import Cursor
from odoo.tools.sql import column_exists, rename_column


def migrate(cr: Cursor, version: str) -> None:
    """Rename ``cached_rate`` to ``cache_read_rate`` on the model catalogue."""
    if column_exists(cr, 'muk_ai_model', 'cached_rate') and not column_exists(
        cr, 'muk_ai_model', 'cache_read_rate'
    ):
        rename_column(cr, 'muk_ai_model', 'cached_rate', 'cache_read_rate')
