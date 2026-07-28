from __future__ import annotations

from odoo import SUPERUSER_ID, api
from odoo.sql_db import Cursor


def migrate(cr: Cursor, version: str) -> None:
    """Retire sessions negotiated under a protocol revision no longer served.

    Every existing session was answered ``2025-03-26``, which this version drops.
    Backfilling them to a supported revision would silently upgrade live clients
    to a protocol they never agreed to, so they are deactivated instead: a client
    that cannot re-handshake on a served revision is one we need to hear about.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    sessions = env['muk_mcp.session'].search([('active', '=', True)])
    if sessions:
        sessions.write({'active': False})
