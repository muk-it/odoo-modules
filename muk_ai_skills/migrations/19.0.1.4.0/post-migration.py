from __future__ import annotations

from odoo.sql_db import Cursor

SCOPES = {
    'muk_ai_skills.skill_reply': 'chatter',
    'muk_ai_skills.demo_skill_log': 'chatter',
    'muk_ai_skills.demo_skill_escalate': 'record',
}


def migrate(cr: Cursor, version: str | None) -> None:
    """Scope the shipped skills on databases that predate the field.

    All three act on the record the user has open, and their data records
    carry ``noupdate="1"``, so the scope added to the XML only reaches fresh
    installs. A skill somebody already scoped keeps its own value.
    """
    for xmlid, scope in SCOPES.items():
        module, name = xmlid.split('.')
        cr.execute(
            """
            UPDATE muk_ai_skill AS skill
            SET scope = %s
            FROM ir_model_data AS data
            WHERE data.module = %s
              AND data.name = %s
              AND data.model = 'muk_ai.skill'
              AND data.res_id = skill.id
              AND (skill.scope IS NULL OR skill.scope = 'any')
            """,
            (scope, module, name),
        )
