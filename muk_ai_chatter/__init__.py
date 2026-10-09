from __future__ import annotations

from odoo import SUPERUSER_ID, api
from odoo.modules.registry import Registry
from odoo.sql_db import Cursor

from . import models


def _post_init_hook(cr: Cursor, registry: Registry) -> None:
    """Give the agents that predate this module their stand-in contact."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['muk_ai.agent'].with_context(active_test=False).search(
        [('partner_id', '=', False)]
    )._provision_partners()
