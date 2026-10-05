from __future__ import annotations

from odoo import models
from odoo.tests import TransactionCase, new_test_user


class CalendarSyncCommon(TransactionCase):
    """Provide a calendar user and a builder for record calendars."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        """Create an administrator owning the calendars, a user and a partner."""
        super().setUpClass()
        cls.admin = new_test_user(
            cls.env,
            login='calendar_sync_admin',
            groups='base.group_user,base.group_system',
        )
        cls.user = new_test_user(cls.env, login='calendar_sync_user')
        cls.partner = cls.env['res.partner'].create({'name': 'Customer'})

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @classmethod
    def _field(cls, model: str, name: str) -> models.BaseModel:
        """Return the field ``name`` of ``model``."""
        return cls.env['ir.model.fields']._get(model, name)

    @classmethod
    def _make_calendar(
        cls, model: str, start: str, user: models.BaseModel | None = None, **values
    ) -> models.BaseModel:
        """Create a calendar of ``user`` showing the records of ``model``."""
        return (
            cls.env['calendar.calendar']
            .with_user(user or cls.admin)
            .create(
                {
                    'name': f'{model} calendar',
                    'source_model_id': cls.env['ir.model']._get_id(model),
                    'source_date_start_field_id': cls._field(model, start).id,
                    **values,
                }
            )
        )

    def _make_activity(self, deadline: str, **values) -> models.BaseModel:
        """Create an activity of the calendar user due on ``deadline``."""
        return self.env['mail.activity'].create(
            {
                'res_model_id': self.env['ir.model']._get_id('res.partner'),
                'res_id': self.partner.id,
                'activity_type_id': self.env.ref('mail.mail_activity_data_todo').id,
                'user_id': self.user.id,
                'date_deadline': deadline,
                **values,
            }
        )

    @staticmethod
    def _event_of(
        calendar: models.BaseModel, record: models.BaseModel
    ) -> models.BaseModel:
        """Return the event that shows ``record`` in ``calendar``."""
        return calendar.sudo()._source_get_events(record)
