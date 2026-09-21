from __future__ import annotations

from odoo import SUPERUSER_ID, api
from odoo.sql_db import Cursor

ANCHOR = 'msg_module_muk_ai_'


def migrate(cr: Cursor, version: str) -> None:
    """Drop the extension settings views this Odoo no longer has a slot for.

    The Extensions block is 19.0-only, so a view grafted onto one of its
    ``msg_module_muk_ai_*`` anchors stops resolving the moment this module's
    settings view is reloaded. Odoo re-validates the whole inheritance tree at
    that point and aborts the upgrade over a view that the addon owning it
    would have removed a few modules later.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    parent = env.ref('muk_ai.view_res_config_settings_form', raise_if_not_found=False)
    if not parent:
        return
    grafts = (
        env['ir.ui.view']
        .sudo()
        .with_context(active_test=False)
        .search([('inherit_id', '=', parent.id), ('arch_db', 'like', ANCHOR)])
    )
    grafts.unlink()
