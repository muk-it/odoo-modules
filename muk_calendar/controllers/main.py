from __future__ import annotations

from odoo import http
from odoo.http import request
from odoo.http.stream import content_disposition
from odoo.tools import consteq


class CalendarSyncController(http.Controller):
    """Serve calendars as iCal feeds behind a secret link."""

    @http.route(
        '/calendar/ical/<int:calendar_id>/<string:token>.ics',
        type='http',
        auth='public',
        methods=['GET'],
        save_session=False,
    )
    def calendar_ical(self, calendar_id: int, token: str) -> http.Response:
        """Return the events of a calendar as an iCalendar document.

        :raise NotFound: when the token is wrong or the owner is inactive
        """
        calendar = request.env['calendar.calendar'].sudo().browse(calendar_id).exists()
        owner = calendar.owner_id
        shared = calendar.ical_token and consteq(calendar.ical_token, token)
        if not (shared and owner.active and not owner.share):
            raise request.not_found()
        return request.make_response(
            calendar._ical_build(),
            headers=[
                ('Content-Type', 'text/calendar; charset=utf-8'),
                (
                    'Content-Disposition',
                    content_disposition(f'{calendar.name or calendar.id}.ics'),
                ),
                ('Cache-Control', 'private, max-age=300'),
            ],
        )
