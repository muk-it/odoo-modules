from __future__ import annotations

from odoo.sql_db import Cursor


def migrate(cr: Cursor, version: str) -> None:
    """Snapshot per-schedule next/last call before owned crons take over."""
    cr.execute("""
        DROP TABLE IF EXISTS _muk_ai_schedule_nextcall_snapshot;
        CREATE TABLE _muk_ai_schedule_nextcall_snapshot AS
        SELECT id, next_call, last_call FROM muk_ai_schedule;
    """)
