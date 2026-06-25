from __future__ import annotations

from odoo import SUPERUSER_ID, api
from odoo.sql_db import Cursor


def migrate(cr: Cursor, version: str) -> None:
    """Recompute the complete name of every partner."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    partners = env['res.partner'].search([])
    partners._compute_complete_name()
