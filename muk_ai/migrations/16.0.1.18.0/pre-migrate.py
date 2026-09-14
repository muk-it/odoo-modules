from __future__ import annotations

from odoo.sql_db import Cursor
from odoo.tools.sql import column_exists, rename_column


def migrate(cr: Cursor, version: str) -> None:
    """Rename ``default_model_id`` to ``default_chat_model_id`` on the providers."""
    if column_exists(cr, 'muk_ai_provider', 'default_model_id') and not column_exists(
        cr, 'muk_ai_provider', 'default_chat_model_id'
    ):
        rename_column(
            cr, 'muk_ai_provider', 'default_model_id', 'default_chat_model_id'
        )
