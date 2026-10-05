from __future__ import annotations

import logging
import secrets
from datetime import date, datetime, time, timedelta

import vobject
from dateutil import tz

from odoo import api, fields, models, tools
from odoo.api import Environment
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.fields import Command, Domain
from odoo.tools.safe_eval import safe_eval

_logger = logging.getLogger(__name__)


class CalendarCalendar(models.Model):
    """Fill a calendar from the records of any model and share it as iCal."""

    _inherit = 'calendar.calendar'

    # ----------------------------------------------------------
    # Properties
    # ----------------------------------------------------------

    @property
    def _source_fields(self) -> frozenset[str]:
        """Return the fields that decide which records the calendar shows."""
        return frozenset(name for name in self._fields if name.startswith('source_'))

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    source_model_id = fields.Many2one(
        comodel_name='ir.model',
        string='Records',
        help='The model whose records the calendar shows as events.',
        groups='base.group_system',
        domain=[('transient', '=', False), ('model', 'not =like', 'calendar.%')],
        ondelete='set null',
    )

    source_model = fields.Char(
        related='source_model_id.model',
        string='Records Model',
        groups='base.group_system',
    )

    source_domain = fields.Char(
        string='Filter',
        help='Only the records matching this filter are shown.',
        default='[]',
        groups='base.group_system',
    )

    source_date_start_field_id = fields.Many2one(
        comodel_name='ir.model.fields',
        string='Date',
        help='The date a record is placed on.',
        groups='base.group_system',
        domain="[('model_id', '=', source_model_id), "
        "('ttype', 'in', ('date', 'datetime')), ('store', '=', True)]",
        ondelete='set null',
    )

    source_date_stop_field_id = fields.Many2one(
        comodel_name='ir.model.fields',
        string='End Date',
        help='The date a record ends on, to show it as a range.',
        groups='base.group_system',
        domain="[('model_id', '=', source_model_id), "
        "('ttype', 'in', ('date', 'datetime')), ('store', '=', True)]",
        ondelete='set null',
    )

    source_partner_field_id = fields.Many2one(
        comodel_name='ir.model.fields',
        string='Attendees',
        help='The contacts or users of a record that attend its event.',
        groups='base.group_system',
        domain="[('model_id', '=', source_model_id), "
        "('ttype', 'in', ('many2one', 'many2many')), "
        "('relation', 'in', ('res.partner', 'res.users'))]",
        ondelete='set null',
    )

    source_allday = fields.Boolean(
        string='All Day',
        help='Show the records as all-day events, even on a date and time.',
        groups='base.group_system',
    )

    source_duration = fields.Float(
        string='Duration',
        help='The length of an event, in hours, when there is no end date.',
        default=1.0,
        groups='base.group_system',
    )

    ical_token = fields.Char(
        string='iCal Token',
        readonly=True,
        copy=False,
        groups='base.group_system',
    )

    ical_scope = fields.Selection(
        selection=[
            ('details', 'Event details'),
            ('busy', 'Busy times only'),
        ],
        string='iCal Content',
        help='What subscribers of the iCal link see of each event.',
        required=True,
        default='details',
    )

    ical_url = fields.Char(
        compute='_compute_ical_url',
        string='iCal Link',
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _owner_env(self) -> Environment:
        """Return the environment of the calendar owner, free of the caller's."""
        self.ensure_one()
        owner = self.owner_id
        return self.env(
            user=owner,
            su=False,
            context={
                'lang': owner.lang,
                'tz': owner.tz,
                'allowed_company_ids': owner.company_ids.ids,
            },
        )

    @api.model
    @api.ormcache()
    def _source_models(self) -> tuple[str, ...]:
        """Return the models whose records some calendar shows."""
        sources = self.sudo().search([('source_model_id', '!=', False)])
        return tuple(sorted(set(sources.mapped('source_model'))))

    def _source_get_domain(self) -> Domain:
        """Return the domain of the records the calendar shows."""
        env = self._owner_env()
        context = {**env['ir.access']._eval_context(), 'uid': env.uid}
        return Domain(safe_eval(self.source_domain or '[]', context)) & Domain(
            self.source_date_start_field_id.name, '!=', False
        )

    def _source_get_events(
        self, records: models.BaseModel | None = None
    ) -> models.BaseModel:
        """Return the events the calendar mirrors, of ``records`` when given."""
        owner = self.sudo().owner_id
        domain = Domain('source_calendar_id', 'in', self.ids)
        if records is not None:
            domain &= Domain('res_id', 'in', records.ids)
        return (
            self.env['calendar.event']
            .sudo()
            .with_context(
                {
                    'active_test': False,
                    'lang': owner.lang,
                    'tz': owner.tz,
                    'dont_notify': True,
                    'mail_create_nolog': True,
                    'no_mail_to_attendees': True,
                    'skip_contact_description': True,
                    'tracking_disable': True,
                }
            )
            .search(domain)
        )

    def _source_get_event_values(self, record: models.BaseModel) -> dict:
        """Return the values of the event that shows a record read by the owner."""
        self.ensure_one()
        start = record[self.source_date_start_field_id.name]
        stop = (
            self.source_date_stop_field_id
            and (record[self.source_date_stop_field_id.name])
        )
        allday = self.source_allday or not isinstance(start, datetime)
        if allday:
            start_date = self._source_get_date(record, start)
            stop_date = max(self._source_get_date(record, stop or start), start_date)
            start = datetime.combine(start_date, time(8))
            stop = datetime.combine(stop_date, time(18))
        elif not stop or stop < start:
            stop = start + timedelta(hours=self.source_duration)
        partners = self.env['res.partner']
        if self.source_partner_field_id:
            partners = record[self.source_partner_field_id.name]
            if partners._name == 'res.users':
                partners = partners.partner_id
        return {
            'name': record.display_name,
            'user_id': self.owner_id.id,
            'calendar_id': self.id,
            'source_calendar_id': self.id,
            'res_model_id': self.source_model_id.id,
            'res_id': record.id,
            'allday': allday,
            'start': start,
            'stop': stop,
            'show_as': 'free',
            'partner_ids': [Command.set(partners.ids)],
            'alarm_ids': [Command.clear()],
            'meeting_activity_ids': [Command.clear()],
        }

    @api.model
    def _source_get_date(
        self, record: models.BaseModel, value: date | datetime
    ) -> date:
        """Return the day of a value in the timezone of ``record``'s environment."""
        if isinstance(value, datetime):
            return fields.Datetime.context_timestamp(record, value).date()
        return value

    @api.model
    def _source_event_differs(self, event: models.BaseModel, values: dict) -> bool:
        """Tell whether an event differs from the values of its record."""
        return (
            event.name != values['name']
            or event.user_id.id != values['user_id']
            or event.res_model_id.id != values['res_model_id']
            or event.allday != values['allday']
            or event.start != values['start']
            or event.stop != values['stop']
            or set(event.partner_ids.ids) != set(values['partner_ids'][0][2])
        )

    def _source_sync(self, records: models.BaseModel | None = None) -> None:
        """Mirror the matching records as events, as the calendar owner reads them.

        Without ``records`` the whole calendar is rebuilt. Only the events the
        calendar created are ever touched.
        """
        for calendar in self.sudo():
            if not (
                calendar.source_model_id
                and calendar.source_date_start_field_id
                and calendar.owner_id
            ):
                calendar._source_get_events(records).unlink()
                continue
            model = calendar._owner_env()[calendar.source_model]
            domain = calendar._source_get_domain()
            if records is not None:
                domain &= Domain('id', 'in', records.ids)
            matches = model.search(domain) if model.has_access('read') else model
            events = calendar._source_get_events(records)
            existing = {event.res_id: event for event in events}
            kept = events.browse(
                existing[record.id].id for record in matches if record.id in existing
            )
            (events - kept).unlink()
            create_values = []
            for record in matches:
                values = calendar._source_get_event_values(record)
                event = existing.get(record.id)
                if not event:
                    create_values.append(values)
                elif self._source_event_differs(event, values):
                    event.write(values)
            events.create(create_values)

    def _source_get_trigger_fields(self) -> models.BaseModel:
        """Return the stored fields whose change can move a record's event."""
        self.ensure_one()
        model = self.env[self.source_model]
        names = {
            'active',
            model._rec_name,
            self.source_date_start_field_id.name,
            self.source_date_stop_field_id.name,
            self.source_partner_field_id.name,
            *(
                path.split('.')[0]
                for path in model.pool.field_depends[model._fields['display_name']]
            ),
            *(
                condition.field_expr.split('.')[0]
                for condition in self._source_get_domain().iter_conditions()
            ),
        }
        return self.env['ir.model.fields'].search(
            [
                ('model', '=', self.source_model),
                ('name', 'in', [name for name in names if name]),
                ('store', '=', True),
            ]
        )

    def _source_get_automations(self) -> models.BaseModel:
        """Return the automations that keep the calendars in sync."""
        return (
            self.env['base.automation']
            .sudo()
            .with_context(active_test=False)
            .search([('action_server_ids.calendar_id', 'in', self.ids)])
        )

    def _source_update_automations(self) -> None:
        """Rebuild the automations that keep each calendar in sync."""
        self._source_get_automations().unlink()
        values = []
        for calendar in self.sudo().filtered(
            lambda cal: cal.source_model_id and cal.source_date_start_field_id
        ):
            name = self.env._('Calendar Sync: %s', calendar.name)
            trigger_fields = calendar._source_get_trigger_fields()
            values += [
                {
                    'name': name,
                    'model_id': calendar.source_model_id.id,
                    'trigger': trigger,
                    'trigger_field_ids': [Command.set(field_ids)],
                    'action_server_ids': [
                        Command.create(
                            {
                                'name': name,
                                'model_id': calendar.source_model_id.id,
                                'state': 'calendar_sync',
                                'calendar_id': calendar.id,
                            }
                        )
                    ],
                }
                for trigger, field_ids in (
                    ('on_create_or_write', trigger_fields.ids),
                    ('on_unlink', []),
                )
            ]
        self.env['base.automation'].sudo().create(values)

    def _ical_build(self) -> str:
        """Serialize the events of the calendar, as its owner sees them."""
        self.ensure_one()
        env = self._owner_env()
        now = fields.Datetime.now()
        events = env['calendar.event'].search(
            [
                ('calendar_id', '=', self.id),
                ('stop', '>=', now - timedelta(days=90)),
                ('start', '<=', now + timedelta(days=365)),
            ]
        )
        uid_domain = self.env['ir.config_parameter'].sudo().get_str('database.uuid')
        busy = env._('Busy')
        calendar = vobject.iCalendar()
        calendar.add('x-wr-calname').value = self.name or ''
        for event in events.read(
            [
                'name',
                'description',
                'location',
                'allday',
                'start',
                'stop',
                'start_date',
                'stop_date',
                'show_as',
                'res_model',
                'res_id',
                'write_date',
            ]
        ):
            vevent = calendar.add('vevent')
            vevent.add('uid').value = f'calendar-event-{event["id"]}@{uid_domain}'
            vevent.add('dtstamp').value = event['write_date'].replace(tzinfo=tz.UTC)
            if event['allday']:
                vevent.add('dtstart').value = event['start_date']
                vevent.add('dtend').value = event['stop_date'] + timedelta(days=1)
            else:
                vevent.add('dtstart').value = event['start'].replace(tzinfo=tz.UTC)
                vevent.add('dtend').value = event['stop'].replace(tzinfo=tz.UTC)
            vevent.add('transp').value = (
                'TRANSPARENT' if event['show_as'] == 'free' else 'OPAQUE'
            )
            if self.ical_scope == 'busy':
                vevent.add('summary').value = busy
                vevent.add('class').value = 'PRIVATE'
                continue
            vevent.add('summary').value = event['name'] or ''
            description = tools.html2plaintext(event['description'] or '')
            if description.strip():
                vevent.add('description').value = description
            if event['location']:
                vevent.add('location').value = event['location']
            if event['res_model'] and event['res_id']:
                vevent.add(
                    'url'
                ).value = (
                    f'{self.get_base_url()}/odoo/{event["res_model"]}/{event["res_id"]}'
                )
        return calendar.serialize()

    # ----------------------------------------------------------
    # Actions
    # ----------------------------------------------------------

    def action_source_sync(self) -> None:
        """Rebuild the events of the calendars from their records.

        :raise AccessError: when the user is not an administrator
        """
        if not self.env.user.has_group('base.group_system'):
            raise AccessError(self.env._('Only administrators can sync calendars.'))
        self._source_sync()

    def action_ical_generate(self) -> None:
        """Create a new secret iCal link, replacing the previous one.

        :raise AccessError: when the user does not own the calendar
        """
        if any(calendar.owner_id != self.env.user for calendar in self):
            raise AccessError(
                self.env._('Only the calendar owner can share it as iCal.')
            )
        for calendar in self.sudo():
            calendar.ical_token = secrets.token_urlsafe(32)

    def action_ical_disable(self) -> None:
        """Remove the iCal link, so subscriptions stop receiving events.

        :raise AccessError: when the user does not own the calendar
        """
        if any(calendar.owner_id != self.env.user for calendar in self):
            raise AccessError(
                self.env._('Only the calendar owner can share it as iCal.')
            )
        self.sudo().ical_token = False

    # ----------------------------------------------------------
    # Compute
    # ----------------------------------------------------------

    @api.depends('ical_token')
    @api.depends_context('uid')
    def _compute_ical_url(self) -> None:
        """Show the iCal link of a calendar to its owner only."""
        for calendar in self:
            token = calendar.sudo().ical_token
            calendar.ical_url = (
                f'{calendar.get_base_url()}/calendar/ical/{calendar.id}/{token}.ics'
                if token and calendar.owner_id == self.env.user
                else False
            )

    # ----------------------------------------------------------
    # Constraints
    # ----------------------------------------------------------

    @api.constrains(lambda self: self._source_fields)
    def _check_source(self) -> None:
        """Require a date field, matching fields and a valid filter for records.

        :raise ValidationError: when the source of a calendar is incomplete
        """
        for calendar in self.sudo().filtered('source_model_id'):
            model = calendar.source_model_id
            start = calendar.source_date_start_field_id
            stop = calendar.source_date_stop_field_id
            partner = calendar.source_partner_field_id
            if not start or start.model_id != model:
                raise ValidationError(
                    self.env._(
                        'Choose the date field the records of %s are placed on.',
                        model.name,
                    )
                )
            if stop and (stop.model_id != model or stop.ttype != start.ttype):
                raise ValidationError(
                    self.env._(
                        'The end date must be a field of the same type as the date.'
                    )
                )
            if partner and partner.model_id != model:
                raise ValidationError(
                    self.env._('The attendees must be a field of %s.', model.name)
                )
            try:
                calendar._owner_env()[model.model].search_count(
                    calendar._source_get_domain(), limit=1
                )
            except (
                AttributeError,
                NameError,
                SyntaxError,
                TypeError,
                ValueError,
            ) as error:
                raise ValidationError(
                    self.env._('The filter of %s is not valid.', calendar.name)
                ) from error

    # ----------------------------------------------------------
    # ORM
    # ----------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list: list[dict]) -> CalendarCalendar:
        """Create the calendars and fill those showing records."""
        calendars = super().create(vals_list)
        sources = calendars.sudo().filtered('source_model_id')
        if sources:
            self.env.transaction.invalidate_ormcache()
            sources._source_update_automations()
            sources._source_sync()
        return calendars

    def write(self, vals: dict) -> bool:
        """Rebuild the events and automations of calendars whose source changes."""
        result = super().write(vals)
        if self._source_fields.intersection(vals):
            self.env.transaction.invalidate_ormcache()
            self._source_update_automations()
            self._source_sync()
        return result

    def unlink(self) -> bool:
        """Delete the calendars together with their automations."""
        self._source_get_automations().unlink()
        result = super().unlink()
        self.env.transaction.invalidate_ormcache()
        return result

    # ----------------------------------------------------------
    # Cron
    # ----------------------------------------------------------

    @api.model
    def _cron_source_sync(self) -> None:
        """Rebuild every calendar showing records, restoring missing automations."""
        for calendar in self.search([('source_model_id', '!=', False)]):
            try:
                with self.env.cr.savepoint():
                    if not calendar._source_get_automations():
                        calendar._source_update_automations()
                    calendar._source_sync()
            except (UserError, ValueError):
                _logger.exception('Calendar %s could not be synced.', calendar.id)
