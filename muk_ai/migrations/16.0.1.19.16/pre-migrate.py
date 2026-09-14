from __future__ import annotations

from odoo.sql_db import Cursor
from odoo.tools.sql import table_exists


def migrate(cr: Cursor, version: str) -> None:
    """Drop the per-domain source icon model, its registrations and its cache.

    The cache is now a plain ``ir.attachment`` per domain, found by the URL it
    is served from, so the old rows are dropped rather than converted: the
    icons are fetched again by the next search citing their domain.
    """
    if not table_exists(cr, 'muk_ai_web_icon'):
        return
    cr.execute("DELETE FROM ir_attachment WHERE res_model = 'muk_ai.web.icon'")
    cr.execute(
        """
        DELETE FROM ir_model_data
              WHERE module = 'muk_ai'
                AND (name LIKE %s OR name IN %s)
        """,
        (
            '%muk_ai_web_icon%',
            ('access_ai_web_icon_user', 'access_ai_web_icon_admin'),
        ),
    )
    cr.execute("DELETE FROM ir_model WHERE model = 'muk_ai.web.icon'")
    cr.execute('DROP TABLE IF EXISTS muk_ai_web_icon CASCADE')
