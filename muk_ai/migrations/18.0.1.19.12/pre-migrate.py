from __future__ import annotations

from odoo.sql_db import Cursor
from odoo.tools.sql import column_exists


def migrate(cr: Cursor, version: str) -> None:
    """Turn the web search toggle into the explicit route selection.

    The toggle never let an admin choose between the app-side backend and
    the vendor connector, so an agent that had it on asked for whichever
    one was available: that is ``automatic``. The column is dropped once
    read, since the field is gone from the model and nothing recreates it.
    """
    if not column_exists(cr, 'muk_ai_agent', 'enable_web_search'):
        return
    cr.execute(
        """
        ALTER TABLE muk_ai_agent ADD COLUMN IF NOT EXISTS web_search varchar;
        UPDATE muk_ai_agent
           SET web_search = CASE WHEN enable_web_search THEN 'auto' ELSE 'off' END
         WHERE web_search IS NULL;
        ALTER TABLE muk_ai_agent DROP COLUMN enable_web_search;
        """
    )
