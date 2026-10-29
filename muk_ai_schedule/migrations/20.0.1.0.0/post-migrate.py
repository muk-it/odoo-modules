from __future__ import annotations

from odoo import SUPERUSER_ID, api
from odoo.sql_db import Cursor

from odoo.addons.base.models.ir_model import MODULE_UNINSTALL_FLAG

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
    """Delete the 1.x views, the space of scheduled chats and the schedules."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    views = env['ir.model.data'].search(
        [
            ('module', '=', 'muk_ai_schedule'),
            ('model', '=', 'ir.ui.view'),
            ('name', 'in', OLD_VIEWS),
        ]
    )
    env['ir.ui.view'].browse(views.mapped('res_id')).unlink()
    if space := env.ref('muk_ai_schedule.space_scheduled', raise_if_not_found=False):
        space.with_context(**{MODULE_UNINSTALL_FLAG: True}).unlink()
    cr.execute(
        """
        DROP TABLE IF EXISTS muk_ai_schedule CASCADE;
        DELETE FROM ir_model_constraint AS constraint_row
         USING ir_module_module AS module
         WHERE module.id = constraint_row.module
           AND module.name = 'muk_ai_schedule'
           AND NOT EXISTS (
               SELECT 1 FROM pg_constraint WHERE conname = constraint_row.name
          )
        """
    )
