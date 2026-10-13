from __future__ import annotations

from odoo import SUPERUSER_ID, api
from odoo.sql_db import Cursor

from odoo.addons.base.models.ir_model import MODULE_UNINSTALL_FLAG


def migrate(cr: Cursor, version: str) -> None:
    """Delete the space of scheduled chats, MuK AI Automation's space lists them."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    if space := env.ref('muk_ai_schedule.space_scheduled', raise_if_not_found=False):
        space.with_context(**{MODULE_UNINSTALL_FLAG: True}).unlink()
