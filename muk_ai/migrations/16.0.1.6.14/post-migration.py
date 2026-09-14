from __future__ import annotations

from odoo.sql_db import Cursor


def migrate(cr: Cursor, version: str) -> None:
    """Drop the obsolete session/attachment relation table."""
    cr.execute('DROP TABLE IF EXISTS muk_ai_session_ir_attachment_rel')
