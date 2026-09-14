from __future__ import annotations

from odoo import SUPERUSER_ID, api
from odoo.sql_db import Cursor


def migrate(cr: Cursor, version: str) -> None:
    """Enable handoff on the General Assistant for existing installs."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    agent = env.ref('muk_ai.agent_general', raise_if_not_found=False)
    if agent and not agent.allow_handoff:
        agent.allow_handoff = True
