from __future__ import annotations

from odoo.sql_db import Cursor


def migrate(cr: Cursor, version: str | None) -> None:
    """Backfill the skill owner from the record creator.

    The upgrade initializes ``owner_id`` with the upgrading user;
    reset it to the original creator so existing skills stay with
    the user who made them.
    """
    cr.execute(
        """
        UPDATE muk_ai_skill
        SET owner_id = create_uid
        WHERE create_uid IS NOT NULL
        """
    )
