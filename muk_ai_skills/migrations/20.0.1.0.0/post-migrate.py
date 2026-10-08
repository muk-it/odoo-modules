from __future__ import annotations

from odoo.sql_db import Cursor

from odoo.addons.muk_ai.tools.icons import material_icon


def migrate(cr: Cursor, version: str | None) -> None:
    """Move the skill icons from Font Awesome classes to Material Symbols."""
    cr.execute("SELECT id, icon FROM muk_ai_skill WHERE icon LIKE 'fa%'")
    rows = cr.fetchall()
    if rows:
        cr.execute(
            """
            UPDATE muk_ai_skill AS skill
               SET icon = mapping.icon
              FROM unnest(%s::int[], %s::varchar[]) AS mapping(id, icon)
             WHERE skill.id = mapping.id
            """,
            [
                [row[0] for row in rows],
                [material_icon(row[1], 'flash_on') for row in rows],
            ],
        )
