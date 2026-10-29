from __future__ import annotations

from odoo import SUPERUSER_ID, api
from odoo.sql_db import Cursor

OLD_VIEWS = (
    'view_ai_session_search_inherit_schedule',
    'view_ai_session_list_inherit_schedule',
    'view_ai_session_form_inherit_schedule',
    'view_muk_ai_schedule_search',
    'view_muk_ai_schedule_list',
    'view_muk_ai_schedule_kanban',
    'view_muk_ai_schedule_form',
)


def migrate(cr: Cursor, version: str | None) -> None:
    """Delete the 1.x views before the modules that extend the session views load."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    views = env['ir.model.data'].search(
        [
            ('module', '=', 'muk_ai_schedule'),
            ('model', '=', 'ir.ui.view'),
            ('name', 'in', OLD_VIEWS),
        ]
    )
    env['ir.ui.view'].browse(views.mapped('res_id')).unlink()
