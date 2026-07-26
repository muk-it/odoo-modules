from __future__ import annotations

import logging

from odoo import SUPERUSER_ID, api
from odoo.sql_db import Cursor

_logger = logging.getLogger(__name__)


def migrate(cr: Cursor, version: str) -> None:
    """Provision owned actions/crons, restore call times, drop the legacy cron."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    Schedule = env['muk_ai.schedule'].sudo()

    rows = Schedule.search([('action_server_id', '=', False)])
    if not rows:
        return

    for schedule in rows:
        schedule._provision_owned_action()

    env.flush_all()

    cr.execute("""
        SELECT s.cron_id, snap.next_call, snap.last_call
        FROM muk_ai_schedule s
        JOIN _muk_ai_schedule_nextcall_snapshot snap ON snap.id = s.id
        WHERE s.cron_id IS NOT NULL
    """)
    for cron_id, nc, lc in cr.fetchall():
        env['ir.cron'].browse(cron_id).sudo().write(
            {
                'nextcall': nc,
                'lastcall': lc,
            }
        )

    cr.execute("""
        UPDATE muk_ai_session
        SET action_server_id = s.action_server_id
        FROM muk_ai_schedule s
        WHERE muk_ai_session.schedule_id = s.id
          AND muk_ai_session.action_server_id IS NULL
    """)

    legacy = env.ref(
        'muk_ai_schedule.cron_fire_due_schedules', raise_if_not_found=False
    )
    if legacy:
        try:
            legacy.sudo().unlink()
        except Exception as exc:  # noqa: BLE001 — legacy cron removal is best-effort
            _logger.warning('could not delete legacy cron: %s', exc)

    cr.execute('DROP TABLE IF EXISTS _muk_ai_schedule_nextcall_snapshot')
