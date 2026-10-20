from __future__ import annotations

from odoo import SUPERUSER_ID, api
from odoo.sql_db import Cursor


def migrate(cr: Cursor, version: str | None) -> None:
    """Let the Writing Assistant answer the writing helpers that had no agent."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    space = env.ref('muk_ai_chatter.space_writing', raise_if_not_found=False)
    if space and not space.agent_id:
        space.agent_id = env.ref('muk_ai_chatter.agent_writer')
