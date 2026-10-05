from __future__ import annotations

from odoo import fields, models
from odoo.fields import Domain


class CalendarEvent(models.Model):
    """Mark the events a record calendar mirrors and hide unreadable ones."""

    _inherit = 'calendar.event'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    source_calendar_id = fields.Many2one(
        comodel_name='calendar.calendar',
        string='Synced By',
        help='The record calendar that mirrors the record of this event.',
        readonly=True,
        index='btree_not_null',
        copy=False,
        ondelete='cascade',
    )

    # ----------------------------------------------------------
    # Compute
    # ----------------------------------------------------------

    def _compute_user_can_edit(self) -> None:
        """Forbid editing a synced event, it follows its record."""
        super()._compute_user_can_edit()
        self.filtered('source_calendar_id').user_can_edit = False

    # ----------------------------------------------------------
    # ORM
    # ----------------------------------------------------------

    def _access_domain(self, operation: str) -> Domain:
        """Hide a synced event from users who may not read its record."""
        domain = super()._access_domain(operation)
        visible = Domain('source_calendar_id', '=', False)
        for model in self.env['calendar.calendar']._source_models():
            records = self.env[model]
            if records.has_access('read'):
                visible |= Domain('res_model', '=', model) & Domain(
                    'res_id', 'in', records._search([])
                )
        return domain & visible
