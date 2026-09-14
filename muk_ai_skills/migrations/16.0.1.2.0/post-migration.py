from __future__ import annotations

from odoo.sql_db import Cursor

ICONS = {
    'muk_ai_skills.skill_reply': 'fa-reply',
    'muk_ai_skills.demo_skill_log': 'fa-sticky-note-o',
    'muk_ai_skills.demo_skill_escalate': 'fa-calendar-plus-o',
}


def migrate(cr: Cursor, version: str | None) -> None:
    """Set the icon of the shipped skills on databases that predate the field.

    Their data records carry ``noupdate="1"``, so the icons added to the
    XML only reach fresh installs. Existing skills keep whatever icon
    they already have.
    """
    for xmlid, icon in ICONS.items():
        module, name = xmlid.split('.')
        cr.execute(
            """
            UPDATE muk_ai_skill AS skill
            SET icon = %s
            FROM ir_model_data AS data
            WHERE data.module = %s
              AND data.name = %s
              AND data.model = 'muk_ai.skill'
              AND data.res_id = skill.id
              AND (skill.icon IS NULL OR skill.icon = '' OR skill.icon = 'fa-bolt')
            """,
            (icon, module, name),
        )
