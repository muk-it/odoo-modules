from __future__ import annotations

from typing import Any

from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import UserError

from odoo.addons.muk_mcp.core.tool import mcp_tool
from odoo.addons.muk_mcp.tools.descriptions import context_field, model_field

RECORD_ID = {'type': 'integer', 'description': 'The record ID.'}


class MCPMixin(models.AbstractModel):
    """Add the MCP chatter and activity tools to the shared MCP mixin."""

    _inherit = 'muk_mcp.mixin'

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _mcp_mail_record(self, model: str, res_id: int, flag: str) -> models.BaseModel:
        """Return the record a chatter tool targets, refusing a model ``flag`` is off for.

        :param flag: ``is_mail_thread`` or ``is_mail_activity`` of ``ir.model``
        :raise UserError: when the model has no chatter or no activities, or the
            record does not exist.
        """
        if model in self.env and not self.env['ir.model']._get(model)[flag]:
            raise UserError(
                self.env._('Records of %s have no chatter.', model)
                if flag == 'is_mail_thread'
                else self.env._('Records of %s have no activities.', model),
            )
        return self._mcp_record(model, res_id)

    @api.model
    def _mcp_activity_type(self, model: str, wanted: str | int | None) -> models.Model:
        """Return the activity type a name, XML ID or ID names, To-Do by default.

        :raise UserError: when no type available on ``model`` matches, naming those
            that are.
        """
        types = self.env['mail.activity.type'].search(
            ['|', ('res_model', '=', False), ('res_model', '=', model)]
        )
        if not wanted:
            found = self.env.ref(
                'mail.mail_activity_data_todo', raise_if_not_found=False
            )
            found = (found & types) or types[:1]
        elif isinstance(wanted, int):
            found = types.filtered(lambda kind: kind.id == wanted)
        elif '.' in wanted:
            found = self.env.ref(wanted, raise_if_not_found=False)
            found = found & types if found else types.browse()
        else:
            found = types.filtered(
                lambda kind: (
                    wanted.lower()
                    in {kind.name.lower(), kind.with_context(lang='en_US').name.lower()}
                )
            )
        if not found:
            raise UserError(
                self.env._(
                    'Activity type %(type)r is not available on %(model)s. Available: %(types)s',
                    type=wanted,
                    model=model,
                    types=', '.join(types.mapped('name')),
                ),
            )
        return found[0]

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    @mcp_tool(
        name='get_messages',
        description=(
            'Get the chatter of a record, newest first: comments, notes, status '
            'changes and field tracking (who changed what and when).'
        ),
        input_schema={
            'type': 'object',
            'properties': {
                'model': model_field(),
                'id': RECORD_ID,
                'limit': {
                    'type': 'integer',
                    'description': 'Maximum number of messages to return.',
                    'default': 20,
                },
                'context': context_field(),
            },
            'required': ['model', 'id'],
        },
        category='read',
    )
    def _mcp_get_messages(self, model: str, id: int, limit: int = 20) -> list[dict]:
        """Return the newest messages of a record with their tracking values."""
        record = self._mcp_mail_record(model, id, 'is_mail_thread')
        messages = self.env['mail.message']
        return messages.search_read(
            [('model', '=', model), ('res_id', '=', record.id)],
            fields=[
                'date',
                'author_id',
                'message_type',
                'subtype_id',
                'body',
                *messages.fields_get(['tracking_value_ids']),
            ],
            limit=limit,
            order='date desc',
        )

    @api.model
    @mcp_tool(
        name='post_message',
        description=(
            "Post on a record's chatter: type 'comment' notifies the followers, "
            "'note' is an internal note only internal users see."
        ),
        input_schema={
            'type': 'object',
            'properties': {
                'model': model_field(),
                'id': RECORD_ID,
                'body': {
                    'type': 'string',
                    'description': 'The message content (can contain HTML).',
                },
                'type': {
                    'type': 'string',
                    'enum': ['comment', 'note'],
                    'default': 'comment',
                },
                'context': context_field(),
            },
            'required': ['model', 'id', 'body'],
        },
        category='write',
    )
    def _mcp_post_message(
        self, model: str, id: int, body: str, type: str = 'comment'
    ) -> dict[str, Any]:
        """Post ``body`` as a comment or an internal note on a record."""
        record = self._mcp_mail_record(model, id, 'is_mail_thread')
        message = record.message_post(
            body=Markup(body),
            message_type='comment',
            subtype_xmlid='mail.mt_note' if type == 'note' else 'mail.mt_comment',
        )
        return {'id': message.id, 'date': fields.Datetime.to_string(message.date)}

    @api.model
    @mcp_tool(
        name='schedule_activity',
        description=(
            'Schedule an activity (to-do, call, meeting, email, ...) on a record '
            "for a user and a due date. The type is a name ('Call'), an XML ID or "
            "an ID, To-Do by default; the due date defaults to the type's delay, "
            'the user to you. Use this instead of creating mail.activity records.'
        ),
        input_schema={
            'type': 'object',
            'properties': {
                'model': model_field(),
                'id': RECORD_ID,
                'activity_type': {
                    'type': ['string', 'integer'],
                    'description': 'Activity type name, XML ID or ID.',
                },
                'summary': {'type': 'string', 'description': 'Short title.'},
                'note': {
                    'type': 'string',
                    'description': 'Details (can contain HTML).',
                },
                'date_deadline': {
                    'type': 'string',
                    'description': 'Due date as YYYY-MM-DD.',
                },
                'user_id': {
                    'type': 'integer',
                    'description': (
                        'ID of another user to assign it to. Omit it to assign '
                        'the activity to yourself.'
                    ),
                },
                'context': context_field(),
            },
            'required': ['model', 'id'],
        },
        category='write',
    )
    def _mcp_schedule_activity(
        self,
        model: str,
        id: int,
        activity_type: str | int | None = None,
        summary: str | None = None,
        note: str | None = None,
        date_deadline: str | None = None,
        user_id: int | None = None,
    ) -> dict[str, Any]:
        """Create an activity, leaving what is not given to the type's defaults."""
        record = self._mcp_mail_record(model, id, 'is_mail_activity')
        if user_id and not self.env['res.users'].browse(user_id).exists().active:
            raise UserError(self.env._('User %s is not an active user.', user_id))
        values = {
            'res_model_id': self.env['ir.model']._get_id(model),
            'res_id': record.id,
            'activity_type_id': self._mcp_activity_type(model, activity_type).id,
            'user_id': user_id or self.env.uid,
        }
        if summary:
            values['summary'] = summary
        if note:
            values['note'] = Markup(note)
        if date_deadline:
            values['date_deadline'] = date_deadline
        activity = self.env['mail.activity'].create(values)
        return {
            'id': activity.id,
            'activity_type': activity.activity_type_id.name,
            'summary': activity.summary or '',
            'date_deadline': fields.Date.to_string(activity.date_deadline),
            'user': activity.user_id.display_name,
        }
