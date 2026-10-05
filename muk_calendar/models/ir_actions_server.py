from __future__ import annotations

from odoo import fields, models


class IrActionsServer(models.Model):
    """Keep a record calendar in sync with the records an automation reports."""

    _inherit = 'ir.actions.server'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    state = fields.Selection(
        selection_add=[('calendar_sync', 'Sync Calendar')],
        ondelete={'calendar_sync': 'cascade'},
    )

    calendar_id = fields.Many2one(
        comodel_name='calendar.calendar',
        string='Calendar',
        help='The calendar whose events follow the records of this action.',
        index='btree_not_null',
        ondelete='cascade',
    )

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    def _run_action_calendar_sync_multi(self, eval_context: dict | None = None) -> bool:
        """Update or remove the events of the reported records."""
        records = eval_context.get('records') or eval_context.get('record')
        if self.base_automation_id.trigger == 'on_unlink':
            self.calendar_id._source_get_events(records).unlink()
        else:
            self.calendar_id._source_sync(records)
        return False

    # ----------------------------------------------------------
    # Compute
    # ----------------------------------------------------------

    def _compute_allowed_states(self) -> None:
        """Keep the calendar sync out of the types offered to users."""
        super()._compute_allowed_states()
        for action in self:
            action.allowed_states = [
                state for state in action.allowed_states if state != 'calendar_sync'
            ]
