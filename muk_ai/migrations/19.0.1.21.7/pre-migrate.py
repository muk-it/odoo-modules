from __future__ import annotations

from odoo.sql_db import Cursor


def migrate(cr: Cursor, version: str) -> None:
    """Turn the system prompt column back into text, keeping the English value.

    The field stopped being translatable, and Odoo leaves the ``jsonb`` column
    behind: every write of a plain string then fails.
    """
    cr.execute(
        """
        SELECT data_type FROM information_schema.columns
        WHERE table_name = 'muk_ai_agent' AND column_name = 'system_prompt'
        """
    )
    row = cr.fetchone()
    if row and row[0] == 'jsonb':
        cr.execute(
            """
            ALTER TABLE muk_ai_agent
            ALTER COLUMN system_prompt TYPE text
            USING system_prompt ->> 'en_US'
            """
        )
