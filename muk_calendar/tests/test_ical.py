from datetime import date, datetime, timedelta

import vobject

from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests import HttpCase, new_test_user


class TestCalendarIcal(HttpCase):
    """Test the iCal link of a calendar through its route."""

    @classmethod
    def setUpClass(cls) -> None:
        """Create a user with events now, next new year and long ago."""
        super().setUpClass()
        cls.user = new_test_user(cls.env, login='calendar_ical_user', lang='en_US')
        cls.calendar = cls.user.with_user(cls.user)._find_or_create_primary_calendar()
        now = fields.Datetime.now().replace(microsecond=0)
        cls.env['calendar.event'].with_user(cls.user).create(
            [
                {
                    'name': 'Board meeting',
                    'description': '<p>Budget review</p>',
                    'location': 'Vienna',
                    'start': now + timedelta(days=1),
                    'stop': now + timedelta(days=1, hours=2),
                },
                {
                    'name': 'Holiday',
                    'allday': True,
                    'start': datetime(now.year + 1, 1, 1, 8),
                    'stop': datetime(now.year + 1, 1, 2, 18),
                },
                {
                    'name': 'Long ago',
                    'start': now - timedelta(days=400),
                    'stop': now - timedelta(days=400, hours=-1),
                },
            ]
        )
        cls.partner = cls.env['res.partner'].create({'name': 'Customer'})
        cls.env['calendar.event'].with_user(cls.user).with_context(
            skip_contact_description=True
        ).create(
            {
                'name': 'Customer visit',
                'start': now + timedelta(days=2),
                'stop': now + timedelta(days=2, hours=1),
                'res_model_id': cls.env['ir.model']._get_id('res.partner'),
                'res_id': cls.partner.id,
            }
        )
        cls.start = now + timedelta(days=1)

    def _fetch(self, url: str) -> dict:
        """Return the events of the iCal feed at ``url`` by summary."""
        response = self.url_open(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/calendar', response.headers['Content-Type'])
        calendar = vobject.readOne(response.text)
        return {event.summary.value: event for event in calendar.vevent_list}

    def test_feed_events(self):
        calendar = self.calendar.with_user(self.user)
        calendar.action_ical_generate()
        events = self._fetch(calendar.ical_url)
        self.assertEqual(set(events), {'Board meeting', 'Holiday', 'Customer visit'})
        visit = events['Customer visit']
        self.assertTrue(
            visit.url.value.endswith(f'/odoo/res.partner/{self.partner.id}')
        )
        self.assertFalse(hasattr(visit, 'description'))
        meeting = events['Board meeting']
        self.assertEqual(meeting.dtstart.value.replace(tzinfo=None), self.start)
        self.assertTrue(meeting.description.value.startswith('Budget review'))
        self.assertEqual(meeting.location.value, 'Vienna')
        holiday = events['Holiday']
        year = self.start.year + 1
        self.assertEqual(holiday.dtstart.value, date(year, 1, 1))
        self.assertEqual(holiday.dtend.value, date(year, 1, 3))
        calendar.ical_scope = 'busy'
        busy = self._fetch(calendar.ical_url)
        self.assertEqual(list(busy), ['Busy'])
        self.assertFalse(hasattr(busy['Busy'], 'description'))

    def test_feed_link_lifecycle(self):
        calendar = self.calendar.with_user(self.user)
        self.assertFalse(calendar.ical_url)
        calendar.action_ical_generate()
        first = calendar.ical_url
        self.assertEqual(self.url_open(first.replace('.ics', 'x.ics')).status_code, 404)
        calendar.action_ical_generate()
        self.assertEqual(self.url_open(first).status_code, 404)
        second = calendar.ical_url
        self.assertEqual(self.url_open(second).status_code, 200)
        self.user.active = False
        self.assertEqual(self.url_open(second).status_code, 404)
        self.user.active = True
        calendar.action_ical_disable()
        self.assertFalse(calendar.ical_url)
        self.assertEqual(self.url_open(second).status_code, 404)

    def test_only_owner_shares(self):
        member = new_test_user(self.env, login='calendar_ical_member')
        self.calendar.with_user(self.user).share_user_ids = member
        self.calendar.with_user(self.user).action_ical_generate()
        calendar = self.calendar.with_user(member)
        self.assertFalse(calendar.ical_url)
        for action in (calendar.action_ical_generate, calendar.action_ical_disable):
            with self.subTest(action=action.__name__), self.assertRaises(AccessError):
                action()
