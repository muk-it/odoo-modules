from __future__ import annotations

from odoo import api, fields, models
from odoo.tools.misc import clean_context
from odoo.tools.safe_eval import safe_eval


class Router(models.TransientModel):
    """Drive the routing of failed messages onto new or existing records."""

    _name = 'muk_mail_route.router'
    _description = 'Router'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    configuration_id = fields.Many2one(
        comodel_name='muk_mail_route.configuration',
        string='Configuration',
        readonly=True,
        ondelete='cascade',
    )

    model = fields.Selection(
        compute='_compute_configuration_values',
        selection=lambda self: self._selection_model(),
        string='Model',
        readonly=False,
        store=True,
    )

    route_type = fields.Selection(
        related='configuration_id.route_type',
        readonly=True,
    )

    res_id = fields.Many2oneReference(
        string='Route Object',
        model_field='model',
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
    def _selection_model(self) -> list[tuple[str, str]]:
        """Return the mail-thread models the current user may target."""
        model_ids = (
            self.env['ir.model']
            .sudo()
            .search(
                [
                    ('access_ids.group_id.user_ids', '=', self.env.uid),
                    ('is_mail_thread', '=', True),
                    ('transient', '=', False),
                ]
            )
        )
        return model_ids.mapped(lambda rec: (rec.model, rec.name))

    @api.model
    def _create_record_from_message(self, configuration, message) -> models.BaseModel:
        """Create a target record from a message via the rule snippet."""
        model = self.env[configuration.model].with_context(
            clean_context(self.env.context)
        )
        eval_context = {
            'message': message,
            'model': model,
        }
        if configuration.code:
            safe_eval(
                configuration.code.strip(),
                eval_context,
                mode='exec',
                filename=str(self),
            )
        return model.create(eval_context.get('values', {}))

    @api.model
    def _create_record_per_messages(self, configuration, messages) -> dict:
        """Create one record per message and return an action listing them."""
        record_ids = []
        for message in messages:
            record = self._create_record_from_message(configuration, message)
            record._mail_route_receive(message)
            record_ids.append(record.id)
        action = (
            configuration.action_id._get_action_dict()
            if configuration.action_id
            else {
                'type': 'ir.actions.act_window',
                'res_model': configuration.model,
                'view_mode': 'list,form',
                'target': 'current',
            }
        )
        action['domain'] = [('id', 'in', record_ids)]
        return action

    # ----------------------------------------------------------
    # Actions
    # ----------------------------------------------------------

    def action_route(self) -> dict:
        """Route the wizard messages to new records, or together to one record."""
        new = self.configuration_id and self.route_type == 'new'
        if new and not self.env.context.get('mail_route_single_record'):
            return self._create_record_per_messages(
                self.configuration_id,
                self.message_ids,
            )
        records = [
            self.env[model].browse(res_id)
            for model, res_id in self.message_ids.grouped(lambda m: (m.model, m.res_id))
        ]
        target = (
            self._create_record_from_message(
                self.configuration_id, self.message_ids.sorted('date')[:1]
            )
            if new
            else self.env[self.model].browse(self.res_id)
        )
        for record in [*records, target]:
            record.check_access('write')
        target._mail_route_receive(
            self.message_ids,
            internal=self.notify and self.set_is_internal,
            notify=self.notify,
        )
        for record in records:
            record._mail_route_log(target)
        return {
            'type': 'ir.actions.act_window',
            'res_model': target._name,
            'res_id': target.id,
            'view_mode': 'form',
            'target': 'current',
        }

    # ----------------------------------------------------------
    # Compute
    # ----------------------------------------------------------

    @api.depends('configuration_id')
    def _compute_configuration_values(self) -> None:
        """Default the model, notify and internal flags from the configuration."""
        self.model, self.notify, self.set_is_internal = False, False, False
        for record in self.filtered('configuration_id'):
            record.model = record.configuration_id.model
            record.notify = record.configuration_id.notify
            record.set_is_internal = record.configuration_id.set_is_internal
