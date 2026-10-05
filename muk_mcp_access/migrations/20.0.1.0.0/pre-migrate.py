from __future__ import annotations

from odoo.sql_db import Cursor


def migrate(cr: Cursor, version: str | None) -> None:
    """Let the update delete the 19.0 noupdate access rules it no longer loads."""
    cr.execute(
        """
        UPDATE ir_model_data
           SET noupdate = FALSE
         WHERE module = 'muk_mcp_access'
           AND model = 'ir.access'
        """
    )
