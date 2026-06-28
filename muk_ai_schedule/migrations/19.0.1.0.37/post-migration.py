from __future__ import annotations

from odoo.sql_db import Cursor


def migrate(cr: Cursor, version: str) -> None:
    """Re-point owned server actions from the legacy ``agent`` state to ``ai_agent``."""
    cr.execute(
        """
        UPDATE ir_act_server s
        SET state = 'ai_agent'
        FROM muk_ai_schedule sch
        WHERE s.id = sch.action_server_id
          AND s.state = 'agent'
        """
    )
