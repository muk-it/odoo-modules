from __future__ import annotations

from odoo import fields, models


class CheckFinding(models.Model):
    """One thing a rule found, with its life from open to resolved or accepted."""

    _name = 'muk_check.finding'
    _description = 'Check Finding'
    _explanation = (
        'Something a check rule found in the database, with why it matters and '
        'how to fix it.'
    )
    _order = 'state, severity, first_seen desc, id desc'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    rule_id = fields.Many2one(
        comodel_name='muk_check.rule',
        string='Rule',
        readonly=True,
        required=True,
        index=True,
        ondelete='cascade',
    )

    name = fields.Char(
        related='rule_id.name',
        string='Finding',
    )

    description = fields.Text(
        related='rule_id.description',
        string='Why It Matters',
    )

    recommendation = fields.Text(
        related='rule_id.recommendation',
        string='How to Fix',
    )

    action_id = fields.Many2one(
        related='rule_id.action_id',
        string='Fix Screen',
    )

    severity = fields.Selection(
        related='rule_id.severity_effective',
        string='Severity',
        store=True,
    )

    category = fields.Selection(
        related='rule_id.category',
        string='Category',
        store=True,
    )

    res_model = fields.Char(
        string='Model',
        readonly=True,
    )

    res_id = fields.Many2oneReference(
        string='Record',
        readonly=True,
        model_field='res_model',
    )

    target = fields.Char(
        string='Where',
        readonly=True,
    )

    detail = fields.Char(
        string='Detail',
        readonly=True,
    )

    state = fields.Selection(
        selection=[
            ('open', 'Open'),
            ('accepted', 'Accepted'),
            ('resolved', 'Resolved'),
        ],
        string='Status',
        readonly=True,
        required=True,
        default='open',
    )

    first_seen = fields.Datetime(
        string='First Seen',
        readonly=True,
        default=fields.Datetime.now,
    )

    last_seen = fields.Datetime(
        string='Last Seen',
        readonly=True,
        default=fields.Datetime.now,
    )

    notified = fields.Boolean(
        string='Notified',
        readonly=True,
    )

    accepted_reason = fields.Text(
        string='Reason',
    )

    accepted_until = fields.Date(
        string='Until',
    )

    accepted_by_id = fields.Many2one(
        comodel_name='res.users',
        string='Accepted By',
        readonly=True,
    )

    # ----------------------------------------------------------
    # Actions
    # ----------------------------------------------------------

    def action_open_details(self) -> dict:
        """Open this finding on its own page."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'views': [(False, 'form')],
        }

    def action_open_record(self) -> dict:
        """Open the record this finding is about."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': self.res_model,
            'res_id': self.res_id,
            'views': [(False, 'form')],
        }

    def action_open_fix(self) -> dict:
        """Open the screen where this finding can be fixed."""
        self.ensure_one()
        return self.action_id._get_action_dict()

    def action_open_accept(self) -> dict:
        """Ask for the reason and the end date of accepting this finding."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Accept Finding'),
            'res_model': self._name,
            'res_id': self.id,
            'views': [(self.env.ref('muk_check.view_check_finding_accept').id, 'form')],
            'target': 'new',
        }

    def action_accept(self) -> None:
        """Stop counting this finding until its end date."""
        self.ensure_one()
        self.write({'state': 'accepted', 'accepted_by_id': self.env.uid})

    def action_reopen(self) -> None:
        """Count this accepted finding again."""
        self.ensure_one()
        self.write(
            {
                'state': 'open',
                'accepted_reason': False,
                'accepted_until': False,
                'accepted_by_id': False,
            }
        )
