from __future__ import annotations

from odoo import SUPERUSER_ID, api
from odoo.sql_db import Cursor

WORKER_CRONS = (
    'muk_ai.cron_run_pending_sessions_1',
    'muk_ai.cron_run_pending_sessions_2',
    'muk_ai.cron_run_pending_sessions_3',
    'muk_ai.cron_run_pending_sessions_4',
)


def migrate(cr: Cursor, version: str) -> None:
    """Let the session workers run more than once.

    ``ir.cron.numbercall`` defaults to 1 on this Odoo and the scheduler
    deactivates a cron once it is used up, so every worker retired after its
    first run and no turn was ever picked up again. ``data/ir_cron.xml`` is
    ``noupdate``, so installs that already retired them need this.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    for xmlid in WORKER_CRONS:
        cron = env.ref(xmlid, raise_if_not_found=False)
        if cron:
            cron.sudo().write({'numbercall': -1, 'active': True})
