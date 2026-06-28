from __future__ import annotations


def migrate(cr, version) -> None:
    """Rename legacy ``agent`` server-action state to ``ai_agent``."""
    cr.execute("UPDATE ir_act_server SET state = 'ai_agent' WHERE state = 'agent'")
