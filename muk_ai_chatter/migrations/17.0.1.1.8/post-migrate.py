from __future__ import annotations

from odoo import SUPERUSER_ID, api
from odoo.sql_db import Cursor


def migrate(cr: Cursor, version: str | None) -> None:
    """Leave the writing helper chats to the Chatter space."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    if space := env.ref('muk_ai_chatter.space_records', raise_if_not_found=False):
        space.domain = "[('res_model', '!=', False), ('compose_interface', '=', False)]"
