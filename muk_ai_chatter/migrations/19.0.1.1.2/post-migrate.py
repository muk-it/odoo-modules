from __future__ import annotations

from odoo.api import Environment
from odoo.sql_db import Cursor


def migrate(cr: Cursor, version: str) -> None:
    """Rename the composer space, which noupdate data leaves untouched."""
    env = Environment(cr, 1, {})
    space = env.ref('muk_ai_chatter.space_writing', raise_if_not_found=False)
    if space and space.name == 'Writing Helper':
        space.name = 'Chatter'
