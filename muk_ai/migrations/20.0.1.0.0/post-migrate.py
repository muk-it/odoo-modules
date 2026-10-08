from __future__ import annotations

from odoo import SUPERUSER_ID, api
from odoo.sql_db import Cursor

from odoo.addons.muk_ai.tools.icons import material_icon


def migrate(cr: Cursor, version: str | None) -> None:
    """Drop the Router agent and move the space icons to Material Symbols."""
    api.Environment(cr, SUPERUSER_ID, {}).ref(
        'muk_ai.agent_router', raise_if_not_found=False
    ).unlink()
    cr.execute("SELECT id, icon FROM muk_ai_space WHERE icon LIKE 'fa%'")
    rows = cr.fetchall()
    if rows:
        cr.execute(
            """
            UPDATE muk_ai_space AS space
               SET icon = mapping.icon
              FROM unnest(%s::int[], %s::varchar[]) AS mapping(id, icon)
             WHERE space.id = mapping.id
            """,
            [[row[0] for row in rows], [material_icon(row[1]) for row in rows]],
        )
