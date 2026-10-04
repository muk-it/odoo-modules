from __future__ import annotations

from odoo.sql_db import Cursor


def migrate(cr: Cursor, version: str | None) -> None:
    """Let the update delete the 19.0 noupdate access rules and drop the old key index."""
    cr.execute(
        """
        UPDATE ir_model_data
           SET noupdate = FALSE
         WHERE module = 'muk_mcp'
           AND model = 'ir.access'
        """
    )
    cr.execute('DROP INDEX IF EXISTS muk_mcp_key_key_hash_idx')
