from __future__ import annotations

from odoo import fields, models


class AIDecisionOption(models.Model):
    """One option of a decision question: a category, or a level of a score."""

    _name = 'muk_ai.decision.option'
    _description = 'AI Decision Option'
    _order = 'sequence, id'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    question_id = fields.Many2one(
        comodel_name='muk_ai.decision.question',
        string='Question',
        required=True,
        index=True,
        ondelete='cascade',
    )

    sequence = fields.Integer(
        string='Sequence',
        default=10,
    )

    name = fields.Char(
        string='Option',
        help='Answer the decision model gives, e.g. "billing".',
        required=True,
    )

    description = fields.Char(
        string='Description',
        help='Hint what the option means, e.g. "payments and invoices".',
    )

    action_id = fields.Many2one(
        comodel_name='ir.actions.server',
        string='Run Action',
        help='Server action run once on all records answered with this option.',
        ondelete='set null',
    )
