from __future__ import annotations

from odoo.sql_db import Cursor


def migrate(cr: Cursor, version: str | None) -> None:
    """Mark the finished chats of agent actions as read."""
    cr.execute(
        """
        UPDATE muk_ai_session
           SET notification_unread = FALSE
         WHERE notification_unread
           AND action_server_id IS NOT NULL
           AND state = 'done'
        """
    )
