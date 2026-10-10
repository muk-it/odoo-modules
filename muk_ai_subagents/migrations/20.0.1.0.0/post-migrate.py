from __future__ import annotations

from odoo import SUPERUSER_ID, api
from odoo.sql_db import Cursor


def migrate(cr: Cursor, version: str | None) -> None:
    """Drop the stall sweep, the subagents space and the run settings."""
    cr.execute(
        "UPDATE muk_ai_session SET stop_reason = 'error' WHERE stop_reason = 'stalled'"
    )
    env = api.Environment(cr, SUPERUSER_ID, {})
    for xmlid in (
        'muk_ai_subagents.cron_sweep_stalled_children',
        'muk_ai_subagents.space_subagents',
    ):
        env.ref(xmlid, raise_if_not_found=False).unlink()
    env['ir.config_parameter'].search(
        [
            (
                'key',
                'in',
                ('muk_ai_subagents.stall_timeout', 'muk_ai_subagents.run_cost_limit'),
            )
        ]
    ).unlink()
