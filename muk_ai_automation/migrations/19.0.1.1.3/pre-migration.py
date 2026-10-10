from __future__ import annotations

from odoo.sql_db import Cursor


def migrate(cr: Cursor, version: str) -> None:
    """Drop the views of this module so the update recreates them from its files.

    The views of the previous release name fields this release removes, and
    Odoo validates them while it loads the new view files.
    """
    cr.execute(
        """
        WITH views AS (
            DELETE FROM ir_model_data
            WHERE module = 'muk_ai_automation' AND model = 'ir.ui.view'
            RETURNING res_id
        )
        DELETE FROM ir_ui_view WHERE id IN (SELECT res_id FROM views)
        """
    )
