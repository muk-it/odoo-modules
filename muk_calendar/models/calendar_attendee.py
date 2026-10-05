from __future__ import annotations

from odoo import models
from odoo.fields import Domain


class CalendarAttendee(models.Model):
    """Hide the attendees of a synced event as the event itself is hidden."""

    _inherit = 'calendar.attendee'

    # ----------------------------------------------------------
    # ORM
    # ----------------------------------------------------------

    def _access_domain(self, operation: str) -> Domain:
        """Restrict the attendees of synced events to their visible events."""
        domain = super()._access_domain(operation)
        synced = self.env['calendar.event']._search(
            [('source_calendar_id', '!=', False)]
        )
        return domain & (
            Domain('event_id.source_calendar_id', '=', False)
            | Domain('event_id', 'in', synced)
        )
