from __future__ import annotations

from odoo import api, models


class IrCron(models.Model):
    """Keep schedule-owned crons aligned with their true recurrence."""

    _inherit = 'ir.cron'

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    def _reschedule_later(self, job: dict) -> None:
        """Re-derive nextcall from the owning schedule after the base advance.

        The base implementation advances nextcall by the cron's fixed
        interval, which cannot represent cron expressions (the owned cron
        runs on a 1-minute carrier interval) or clamped monthdays (a
        relativedelta month step never returns from the 28th to the 31st).
        """
        super()._reschedule_later(job)
        schedule = (
            self.env['muk_ai.schedule']
            .sudo()
            .search([('cron_id', '=', job['id'])], limit=1)
        )
        if schedule and schedule.interval_type in ('cron', 'months'):
            self.browse(job['id']).invalidate_recordset(['nextcall'])
            schedule._recompute_next_call_on_cron()
