from __future__ import annotations

from odoo.sql_db import Cursor


def migrate(cr: Cursor, version: str) -> None:
    """Raise the hosted providers still on the old output cap to the new default."""
    cr.execute(
        """
        UPDATE muk_ai_provider
           SET max_tokens = 16384
         WHERE max_tokens = 4096
           AND name != 'openai_compat'
        """
    )
