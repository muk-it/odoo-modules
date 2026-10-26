from __future__ import annotations

from odoo import SUPERUSER_ID, api
from odoo.sql_db import Cursor


def migrate(cr: Cursor, version: str | None) -> None:
    """Give the stand-in contacts of the agents the agent's image."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['muk_ai.agent'].with_context(active_test=False).search(
        [('partner_id', '!=', False)]
    )._provision_partners()
