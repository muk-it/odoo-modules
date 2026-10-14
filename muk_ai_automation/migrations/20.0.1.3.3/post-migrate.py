from __future__ import annotations

from odoo import SUPERUSER_ID, api
from odoo.sql_db import Cursor

DOMAINS = {
    'space_automation': (
        "[('action_server_id', '!=', False), ('action_server_usage', '!=', 'ir_cron'), "
        "('action_space_id', '=', False)]"
    ),
    'space_scheduled': (
        "[('action_server_usage', '=', 'ir_cron'), ('action_space_id', '=', False)]"
    ),
}


def migrate(cr: Cursor, version: str | None) -> None:
    """Filter the automation spaces on fields of the chat users may read."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    for name, domain in DOMAINS.items():
        if space := env.ref(f'muk_ai_automation.{name}', raise_if_not_found=False):
            space.domain = domain
