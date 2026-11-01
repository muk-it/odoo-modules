from __future__ import annotations

from odoo import SUPERUSER_ID, api
from odoo.sql_db import Cursor


def migrate(cr: Cursor, version: str | None) -> None:
    """Keep the Writing Assistant out of the agent picker of a chat."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    if agent := env.ref('muk_ai_chatter.agent_writer', raise_if_not_found=False):
        agent.allow_chat = False
