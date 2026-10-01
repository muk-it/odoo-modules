from __future__ import annotations

from odoo.modules.registry import Registry
from odoo.sql_db import Cursor


def migrate(cr: Cursor, version: str) -> None:
    """Turn the system prompt back into an untranslated text column.

    The field stopped being translatable, but while ``ir_model_fields`` still
    marks it translated, Odoo patches it back to translated during every
    upgrade and leaves the ``jsonb`` column behind. Clearing the flag in the
    database and in the running upgrade lets the field load as plain text.
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
    cr.execute(
        """
        UPDATE ir_model_fields SET translate = NULL
        WHERE model = 'muk_ai.agent' AND name = 'system_prompt'
        """
    )
    Registry(cr.dbname)._database_translated_fields.pop(
        'muk_ai.agent.system_prompt', None
    )
