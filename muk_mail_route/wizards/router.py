from __future__ import annotations

from odoo import api, fields, models
from odoo.tools.safe_eval import safe_eval


class Router(models.TransientModel):
    """Drive the routing of failed messages onto new or existing records."""

    _name = 'muk_mail_route.router'
    _description = 'Router'

    # ----------------------------------------------------------
    # Selection
    # ----------------------------------------------------------

    @api.model
    def _selection_reference(self) -> list[tuple[str, str]]:
        """Return the mail-thread models the current user may target."""
        model_ids = (
            self.env['ir.model']
            .sudo()
            .search(
                [
                    ('access_ids.group_id.users', '=', self.env.uid),
                    ('is_mail_thread', '=', True),
                    ('transient', '=', False),
                ]
            )
        )
        return model_ids.mapped(lambda rec: (rec.model, rec.name))

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    configuration_id = fields.Many2one(
        comodel_name='muk_mail_route.configuration',
        string='Configuration',
        readonly=True,
        ondelete='cascade',
    )

    model_id = fields.Many2one(
        related='configuration_id.model_id',
        readonly=True,
    )

    route_type = fields.Selection(
        related='configuration_id.route_type',
        readonly=True,
    )

    reference = fields.Reference(
        selection=lambda self: self._selection_reference(),
        string='Route Object',
    )

    notify = fields.Boolean(
        compute='_compute_configuration_values',
        string='Notify Followers',
        readonly=False,
        store=True,
    )

    set_is_internal = fields.Boolean(
        compute='_compute_configuration_values',
        string='Set Internal',
        readonly=False,
        store=True,
        help='If this option is set, all routed messages are set to internal.',
    )

    message_ids = fields.Many2many(
        comodel_name='mail.message',
        relation='mail_message_wizard_rel',
        column1='message_id',
        column2='wizard_id',
        string='Messages',
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _attach_messages(self, messages, record) -> None:
        """Move the messages and their attachments onto the target record."""
        messages.sudo().write(
            {
                'model': record._name,
                'res_id': record.id,
                'record_name': record.display_name,
            }
        )
        messages.sudo().mapped('attachment_ids').write(
            {
                'res_model': record._name,
                'res_id': record.id,
            }
        )

    @api.model
    def _create_record_from_messages(self, configuration, message) -> int:
        """Create a target record from a message via the rule snippet."""
        eval_context = {
            'message': message,
            'model': self.env[configuration.model],
        }
        if configuration.code:
            safe_eval(
                configuration.code.strip(),
                eval_context,
                mode='exec',
                nocopy=True,
                filename=str(self),
            )
        record = self.env[configuration.model].create(eval_context.get('values', {}))
        self._attach_messages(message, record)
        return record.id

    @api.model
    def _create_record_per_messages(self, configuration, messages) -> dict:
        """Create one record per message and return an action listing them."""
        record_ids = [
            self._create_record_from_messages(configuration, message)
            for message in messages
        ]
        action = (
            configuration.action_id._get_action_dict()
            if configuration.action_id
            else {
                'type': 'ir.actions.act_window',
                'res_model': configuration.model,
                'view_mode': 'tree,form',
                'target': 'current',
            }
        )
        action['domain'] = [('id', 'in', record_ids)]
        return action

    @api.model
    def _notify_messages(self, messages, record, internal: bool) -> None:
        """Notify the record followers about the routed messages."""
        if internal:
            messages.write({'is_internal': True})
        for message in messages:
            record._notify_thread(message)

    @api.model
    def _attach_messages_to_record(
        self, messages, record, internal: bool, notify: bool
    ) -> dict:
        """Attach the messages to an existing record and open its form."""
        self._attach_messages(messages, record)
        if notify:
            self._notify_messages(messages, record, internal)
        return {
            'type': 'ir.actions.act_window',
            'res_model': record._name,
            'res_id': record.id,
            'view_mode': 'form',
            'target': 'current',
        }

    # ----------------------------------------------------------
    # Actions
    # ----------------------------------------------------------

    def action_route(self) -> dict:
        """Route the wizard messages to a new or an existing record."""
        if self.configuration_id and self.route_type == 'new':
            return self._create_record_per_messages(
                self.configuration_id,
                self.message_ids,
            )
        return self._attach_messages_to_record(
            self.message_ids,
            self.reference,
            self.set_is_internal,
            self.notify,
        )

    # ----------------------------------------------------------
    # Compute
    # ----------------------------------------------------------

    @api.depends('configuration_id')
    def _compute_configuration_values(self) -> None:
        """Default the notify and internal flags from the configuration."""
        self.notify, self.set_is_internal = False, False
        for record in self.filtered('configuration_id'):
            record.notify = record.configuration_id.notify
            record.set_is_internal = record.configuration_id.set_is_internal
