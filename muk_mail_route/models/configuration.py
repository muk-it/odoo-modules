from __future__ import annotations

import textwrap

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.safe_eval import test_python_expr


class Configuration(models.Model):
    """Store a routing rule mapping a target model to record-building code."""

    _name = 'muk_mail_route.configuration'
    _description = 'Router Configuration'
    _order = 'sequence'

    # ----------------------------------------------------------
    # Defaults
    # ----------------------------------------------------------

    def _default_code(self) -> str:
        """Return the default record-building snippet for a new rule."""
        return textwrap.dedent("""\
            values = {}
            name_field = model._rec_name or 'name'
            email_field = model._mail_get_primary_email_field()
            if name_field in model._fields and message.subject:
                values[name_field] = message.subject
            if email_field in model._fields and message.email_from:
                values[email_field] = message.email_from
        """)

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    name = fields.Char(
        string='Name',
        translate=True,
        required=True,
    )

    sequence = fields.Integer(
        string='Sequence',
        default=10,
    )

    model_id = fields.Many2one(
        comodel_name='ir.model',
        string='Model',
        domain=[
            ('is_mail_thread', '=', True),
            ('transient', '=', False),
        ],
        required=True,
        ondelete='cascade',
    )

    model = fields.Char(
        related='model_id.model',
        string='Model Name',
    )

    route_type = fields.Selection(
        selection=[
            ('new', 'New Record'),
            ('search', 'Existing Record'),
        ],
        string='Route Type',
        default='new',
        required=True,
    )

    action_id = fields.Many2one(
        comodel_name='ir.actions.act_window',
        string='Action',
        domain="[('res_model', '=', model)]",
        ondelete='set null',
    )

    code = fields.Text(
        string='Code',
        default=lambda self: self._default_code(),
    )

    notify = fields.Boolean(
        string='Notify Followers',
        default=False,
    )

    set_is_internal = fields.Boolean(
        string='Set Internal',
        default=False,
        help='If this option is set, all routed messages are set to internal.',
    )

    # ----------------------------------------------------------
    # Constrains
    # ----------------------------------------------------------

    @api.constrains('code')
    def _check_python_code(self) -> None:
        """Validate the record-building snippet of each rule.

        :raise ValidationError: when the code fails the safe-eval check
        """
        for record in self.sudo().filtered('code'):
            warning = test_python_expr(expr=record.code.strip(), mode='exec')
            if warning:
                raise ValidationError(warning)

    # ----------------------------------------------------------
    # ORM
    # ----------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list: list[dict]) -> Configuration:
        """Create the rules and clear the templates cache."""
        res = super().create(vals_list)
        self.env.registry.clear_cache('templates')
        return res

    def write(self, vals: dict) -> bool:
        """Update the rules and clear the templates cache."""
        res = super().write(vals)
        self.env.registry.clear_cache('templates')
        return res

    def unlink(self) -> bool:
        """Clear the templates cache and delete the rules."""
        self.env.registry.clear_cache('templates')
        return super().unlink()
