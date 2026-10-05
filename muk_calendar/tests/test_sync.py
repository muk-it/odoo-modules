from datetime import date, datetime, timedelta

from odoo.exceptions import AccessError, ValidationError
from odoo.tests import new_test_user

from odoo.addons.muk_calendar.tests.common import CalendarSyncCommon


class TestCalendarSync(CalendarSyncCommon):
    """Test that record calendars follow their records."""

    def test_events_follow_records(self):
        keep = self._make_activity('2026-11-02', summary='Keep')
        drop = self._make_activity('2026-11-03', summary='Drop')
        calendar = self._make_calendar(
            'mail.activity',
            'date_deadline',
            source_domain="[('summary', '=', 'Keep')]",
            source_partner_field_id=self._field('mail.activity', 'user_id').id,
            share_user_ids=self.user.ids,
        )
        event = self._event_of(calendar, keep)
        self.assertRecordValues(
            event,
            [
                {
                    'name': keep.display_name,
                    'allday': True,
                    'start_date': date(2026, 11, 2),
                    'user_id': self.admin.id,
                    'show_as': 'free',
                    'partner_ids': self.user.partner_id.ids,
                    'alarm_ids': [],
                    'description': False,
                }
            ],
        )
        self.assertEqual(self.partner.activity_ids, keep | drop)
        self.assertFalse(self._event_of(calendar, drop))
        for user in (self.admin, self.user):
            with self.subTest(user=user.login):
                self.assertFalse(event.with_user(user).user_can_edit)
        keep.with_user(self.user).date_deadline = '2026-12-24'
        self.assertEqual(event.start_date, date(2026, 12, 24))
        drop.summary = 'Keep'
        self.assertTrue(self._event_of(calendar, drop))
        keep.summary = 'Drop'
        self.assertFalse(event.exists())
        drop.unlink()
        self.assertFalse(calendar.sudo()._source_get_events())

    def test_meetings_stay_untouched(self):
        activity = self._make_activity('2026-11-02')
        calendar = self._make_calendar('mail.activity', 'date_deadline')
        meeting = (
            self.env['calendar.event']
            .with_user(self.admin)
            .create(
                {
                    'name': 'Talk about the activity',
                    'start': datetime(2026, 11, 2, 9, 0),
                    'stop': datetime(2026, 11, 2, 10, 0),
                    'res_model_id': self.env['ir.model']._get_id('mail.activity'),
                    'res_id': activity.id,
                }
            )
        )
        meeting.calendar_id = calendar
        calendar.write({'source_domain': "[('summary', '=', 'None')]"})
        self.assertRecordValues(
            meeting.with_user(self.admin),
            [{'name': 'Talk about the activity', 'user_can_edit': True}],
        )
        self.assertFalse(calendar.sudo()._source_get_events())

    def test_event_dates(self):
        cron = self.env.ref('muk_calendar.cron_source_sync')
        start = datetime(2026, 11, 2, 9, 0)
        cron.write({'nextcall': start, 'lastcall': start + timedelta(hours=3)})
        stop_field = self._field('ir.cron', 'lastcall').id
        cases = [
            ({}, {'allday': False, 'start': start, 'stop': start + timedelta(hours=1)}),
            (
                {'source_duration': 2.5},
                {'allday': False, 'stop': start + timedelta(hours=2.5)},
            ),
            (
                {'source_date_stop_field_id': stop_field},
                {'allday': False, 'stop': start + timedelta(hours=3)},
            ),
            ({'source_allday': True}, {'allday': True, 'start_date': start.date()}),
        ]
        for values, expected in cases:
            with self.subTest(values=values):
                calendar = self._make_calendar(
                    'ir.cron',
                    'nextcall',
                    source_domain=f"[('id', '=', {cron.id})]",
                    **values,
                )
                self.assertRecordValues(self._event_of(calendar, cron), [expected])

    def test_owner_context_decides(self):
        company = self.env['res.company'].create({'name': 'Other Company'})
        editor = new_test_user(
            self.env,
            login='calendar_sync_editor',
            groups='base.group_user,base.group_system',
            company_id=company.id,
            company_ids=[(6, 0, [company.id, self.env.company.id])],
            tz='America/New_York',
        )
        self.admin.tz = 'Pacific/Auckland'
        cron = self.env.ref('muk_calendar.cron_source_sync')
        calendar = self._make_calendar(
            'ir.cron',
            'nextcall',
            source_domain=f"[('id', '=', {cron.id})]",
            source_allday=True,
        )
        cron.with_user(editor).with_context(allowed_company_ids=company.ids).write(
            {'nextcall': datetime(2026, 11, 2, 20, 0)}
        )
        self.assertEqual(self._event_of(calendar, cron).start_date, date(2026, 11, 3))

    def test_owner_access_limits_records(self):
        self.env['ir.access'].create(
            {
                'name': 'Hide partners',
                'model_id': self.env['ir.model']._get_id('res.partner'),
                'operation': 'r',
                'domain': "[('name', '!=', 'Hidden')]",
            }
        )
        partners = self.env['res.partner'].create(
            [
                {'name': 'Visible', 'parent_id': self.partner.id},
                {'name': 'Hidden', 'parent_id': self.partner.id},
            ]
        )
        calendar = self._make_calendar(
            'res.partner',
            'create_date',
            source_domain=f"[('id', 'in', {partners.ids})]",
            source_partner_field_id=self._field('res.partner', 'parent_id').id,
        )
        self.assertRecordValues(
            calendar.sudo()._source_get_events(),
            [{'res_id': partners[0].id, 'partner_ids': self.partner.ids}],
        )

    def test_viewers_see_what_they_may_read(self):
        self.env['ir.access'].create(
            {
                'name': 'Hide partners from users',
                'model_id': self.env['ir.model']._get_id('res.partner'),
                'operation': 'r',
                'domain': "[(1, '=', 1)] if user.has_group('base.group_system') "
                "else [('name', '!=', 'Hidden')]",
            }
        )
        partners = self.env['res.partner'].create(
            [{'name': 'Shown'}, {'name': 'Hidden'}]
        )
        calendars = self._make_calendar(
            'res.partner',
            'create_date',
            source_domain=f"[('id', 'in', {partners.ids})]",
            source_partner_field_id=self._field('res.partner', 'parent_id').id,
            share_user_ids=self.user.ids,
        ) | self._make_calendar('ir.cron', 'nextcall', share_user_ids=self.user.ids)
        partners.parent_id = self.partner
        events = calendars.sudo()._source_get_events()
        shown = events.filtered(lambda event: event.res_id == partners[0].id)
        cases = [(self.admin, events), (self.user, shown)]
        for user, visible in cases:
            with self.subTest(user=user.login):
                found = (
                    self.env['calendar.event']
                    .with_user(user)
                    .search([('calendar_id', 'in', calendars.ids)])
                )
                self.assertEqual(found, visible)
                attendees = (
                    self.env['calendar.attendee']
                    .with_user(user)
                    .search([('event_id', 'in', events.ids)])
                )
                self.assertEqual(attendees.event_id, visible & attendees.event_id)
                self.assertTrue(attendees)
        with self.assertRaises(AccessError):
            (events - shown)[:1].with_user(self.user).read(['name'])

    def test_automations_belong_to_their_calendar(self):
        activity = self._make_activity('2026-11-02')
        calendar = self._make_calendar('mail.activity', 'date_deadline')
        second = self._make_calendar('mail.activity', 'date_deadline')
        automations = calendar.sudo()._source_get_automations()
        self.assertEqual(
            sorted(automations.mapped('trigger')), ['on_create_or_write', 'on_unlink']
        )
        self.assertEqual(
            automations.action_server_ids.mapped('state'), ['calendar_sync'] * 2
        )
        self.assertIn('date_deadline', automations.trigger_field_ids.mapped('name'))
        self.assertNotIn(
            'calendar_sync', automations.action_server_ids[0].allowed_states
        )
        cron = self.env.ref('muk_calendar.cron_source_sync')
        calendar.write(
            {
                'source_model_id': self.env['ir.model']._get_id('ir.cron'),
                'source_date_start_field_id': self._field('ir.cron', 'nextcall').id,
                'source_domain': f"[('id', '=', {cron.id})]",
            }
        )
        self.assertFalse(automations.exists())
        self.assertEqual(calendar.sudo()._source_get_events().res_id, cron.id)
        self.assertEqual(
            calendar.sudo()._source_get_automations().model_id.model, 'ir.cron'
        )
        calendar.write({'source_model_id': False})
        self.assertFalse(calendar.sudo()._source_get_events())
        self.assertFalse(calendar.sudo()._source_get_automations())
        others = second.sudo()._source_get_automations()
        second.sudo().unlink()
        self.assertFalse(others.exists())
        self.assertFalse(
            self.env['calendar.event'].search(
                [
                    ('res_id', '=', activity.id),
                    ('source_calendar_id', '!=', False),
                    ('calendar_id', '!=', calendar.id),
                ]
            )
        )

    def test_removed_date_field_keeps_calendar(self):
        model = self.env['ir.model']._get('res.partner')
        field = self.env['ir.model.fields'].create(
            {'name': 'x_follow_up', 'ttype': 'date', 'model_id': model.id}
        )
        self.partner.x_follow_up = '2026-11-02'
        calendar = self._make_calendar(
            'res.partner',
            'x_follow_up',
            source_domain=f"[('id', '=', {self.partner.id})]",
        )
        filtered = self._make_calendar(
            'res.partner',
            'create_date',
            source_domain="[('x_follow_up', '!=', False)]",
        )
        meeting = self.env['calendar.event'].create(
            {
                'name': 'Planning',
                'start': datetime(2026, 11, 2, 9, 0),
                'stop': datetime(2026, 11, 2, 10, 0),
                'user_id': self.admin.id,
            }
        )
        meeting.calendar_id = calendar
        self.assertTrue(self._event_of(calendar, self.partner))
        field.unlink()
        with self.assertLogs('odoo.addons.muk_calendar', level='ERROR'):
            self.env['calendar.calendar']._cron_source_sync()
        self.assertTrue(filtered.sudo()._source_get_events())
        self.assertTrue(calendar.exists())
        self.assertTrue(meeting.exists())
        self.assertFalse(calendar.sudo()._source_get_events())

    def test_resync_restores_events(self):
        activity = self._make_activity('2026-11-02')
        calendar = self._make_calendar('mail.activity', 'date_deadline')
        resyncs = [
            calendar.action_source_sync,
            self.env['calendar.calendar']._cron_source_sync,
        ]
        for resync in resyncs:
            with self.subTest(resync=resync.__name__):
                self._event_of(calendar, activity).unlink()
                resync()
                self.assertTrue(self._event_of(calendar, activity))
        calendar.sudo()._source_get_automations().unlink()
        self.env['calendar.calendar']._cron_source_sync()
        self.assertEqual(len(calendar.sudo()._source_get_automations()), 2)
        with self.assertRaises(AccessError):
            calendar.with_user(self.user).action_source_sync()

    def test_invalid_source(self):
        cases = [
            {'source_date_start_field_id': False},
            {'source_date_start_field_id': self._field('ir.cron', 'nextcall').id},
            {
                'source_date_stop_field_id': self._field(
                    'mail.activity', 'create_date'
                ).id
            },
            {'source_partner_field_id': self._field('res.partner', 'user_id').id},
            {'source_domain': "[('no_such_field', '=', 1)]"},
            {'source_domain': '[('},
            {'source_domain': '1'},
        ]
        for values in cases:
            with self.subTest(values=values), self.assertRaises(ValidationError):
                self._make_calendar('mail.activity', 'date_deadline', **values)
