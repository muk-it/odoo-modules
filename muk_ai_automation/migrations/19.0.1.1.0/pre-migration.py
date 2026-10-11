from __future__ import annotations

from odoo.sql_db import Cursor

MOVED_FIELDS = (
    'field_muk_ai_session__res_model',
    'field_muk_ai_session__res_id',
)


def migrate(cr: Cursor, version: str) -> None:
    """Drop the external ids of the fields that moved to ``muk_ai_chatter``.

    ``res_model`` and ``res_id`` are now declared by ``muk_ai_chatter``, which
    reflects them under its own external ids while this module still owns the
    original rows. Left in place, those rows would be stale by the end of this
    module's update and Odoo would delete the fields — and their columns — with
    every linked session on them. Removing the external id only unhooks the
    bookkeeping; the fields themselves stay, now owned by ``muk_ai_chatter``.
    """
    cr.execute(
        """
        DELETE FROM ir_model_data
        WHERE module = 'muk_ai_automation'
          AND model = 'ir.model.fields'
          AND name IN %s
        """,
        (MOVED_FIELDS,),
    )
