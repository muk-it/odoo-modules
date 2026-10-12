from __future__ import annotations

from odoo.sql_db import Cursor


def migrate(cr: Cursor, version: str | None) -> None:
    """Run the agent steps of automation rules as the users who created them."""
    cr.execute(
        """
        UPDATE base_automation AS rule
           SET agent_user_id = action.create_uid
          FROM ir_act_server AS action
         WHERE action.base_automation_id = rule.id
           AND action.state = 'ai_agent'
        """
    )
