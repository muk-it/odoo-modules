from __future__ import annotations

from odoo.sql_db import Cursor


def migrate(cr: Cursor, version: str | None) -> None:
    """Release the shipped skills locked to OdooBot, their archived author.

    ``create`` used to seed the share list with the owner unconditionally, so
    records authored by OdooBot ended up private to a login nobody uses,
    while reading the share list showed nothing and the form claimed the
    skill was visible to everyone.

    Restricted to rows owned by and shared with OdooBot alone. A skill a real
    user made private keeps its restriction when that user is archived --
    losing an account must never publish someone's work.
    """
    cr.execute(
        """
        DELETE FROM muk_ai_skill_res_users_rel AS rel
        USING muk_ai_skill AS skill
        WHERE rel.skill_id = skill.id
          AND rel.user_id = 1
          AND skill.owner_id = 1
          AND NOT EXISTS (
              SELECT 1
              FROM muk_ai_skill_res_users_rel AS other
              WHERE other.skill_id = skill.id
                AND other.user_id != 1
          )
        """
    )
