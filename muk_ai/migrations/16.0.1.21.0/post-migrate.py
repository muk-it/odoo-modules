from __future__ import annotations

from odoo import SUPERUSER_ID, api
from odoo.sql_db import Cursor


def migrate(cr: Cursor, version: str) -> None:
    """Pin the shared space, which ships pinned but predates the field.

    ``data/space.xml`` is ``noupdate``, so a record already on the database
    keeps the values it was created with and never sees the new one. Without
    this the one space meant to survive the collapsed automatic section would
    fold away with the rest on every existing install.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    space = env.ref('muk_ai.space_shared', raise_if_not_found=False)
    if space and not space.pinned:
        space.pinned = True
