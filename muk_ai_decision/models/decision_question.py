from __future__ import annotations

from odoo import api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.muk_ai_decision.tools.field_question import FIELD_TYPES, FieldQuestion


class AIDecisionQuestion(models.Model):
    """One question a Decide with AI action asks about each record."""

    _name = 'muk_ai.decision.question'
    _description = 'AI Decision Question'
    _explanation = (
        'A question of a Decide with AI server action: a choice, a score or a '
        'yes/no, either typed in or derived from the target field it fills, '
        'with the confidence an answer needs before it is written, and the '
        'action run on the records with a given answer.'
    )
    _order = 'sequence, id'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    action_id = fields.Many2one(
        comodel_name='ir.actions.server',
        string='Action',
        required=True,
        index=True,
        ondelete='cascade',
    )

    model_id = fields.Many2one(
        related='action_id.model_id',
    )

    sequence = fields.Integer(
        string='Sequence',
        default=10,
    )

    name = fields.Char(
        string='Question',
        help=(
            'What the decision model is asked, e.g. "Which team should handle '
            'this ticket?". Optional with a target field, which names it.'
        ),
        translate=True,
    )

    field_id = fields.Many2one(
        comodel_name='ir.model.fields',
        string='Target Field',
        help=(
            'Field the confident answer is written to. Its values are the '
            'options: the selection, the candidate records, or one yes/no '
            'question per tag.'
        ),
        domain=(
            "[('model_id', '=', model_id), ('store', '=', True), "
            f"('ttype', 'in', {list(FIELD_TYPES)})]"
        ),
        ondelete='cascade',
    )

    field_label = fields.Char(
        related='field_id.field_description',
    )

    field_type = fields.Selection(
        related='field_id.ttype',
    )

    field_relation = fields.Char(
        related='field_id.relation',
    )

    kind = fields.Selection(
        compute='_compute_kind',
        precompute=True,
        selection=[
            ('choice', 'Choice'),
            ('score', 'Score'),
            ('noul', 'Yes/No'),
        ],
        string='Type',
        help='Choice picks one option, Score rates on ordered levels.',
        readonly=False,
        required=True,
        store=True,
    )

    options = fields.Text(
        string='Options',
        help=(
            'Without a target field: one option per line, or one level per line '
            'from lowest to highest for a score. "label: description" adds a hint.'
        ),
    )

    candidate_domain = fields.Char(
        string='Candidates',
        help='Filter on the records a many2one or tags field may be set to.',
        default='[]',
    )

    route_answer = fields.Char(
        string='Route Answer',
        help=(
            'Answer that runs the route action: an option, a level or a tag name, '
            'or "yes" or "no".'
        ),
    )

    route_action_id = fields.Many2one(
        comodel_name='ir.actions.server',
        string='Run Action',
        help='Server action run once on all records answered with the route answer.',
        domain="[('model_id', '=', model_id), ('id', '!=', action_id)]",
        ondelete='set null',
    )

    min_confidence = fields.Float(
        string='Min. Confidence',
        help='Confidence an answer needs before it is written or routed.',
        default=0.8,
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _options(self) -> dict:
        """Parse the typed options into a label to description map."""
        options = {}
        for line in (self.options or '').splitlines():
            label, _sep, description = line.partition(':')
            if label.strip():
                options[label.strip()] = description.strip() or None
        return options

    def _spec(self) -> FieldQuestion:
        """Return the questions this line asks and the value of each answer."""
        self.ensure_one()
        if self.field_id:
            return self.env['muk_ai.decision']._field_question(
                self.action_id.model_name,
                self.field_id.name,
                self.name,
                self.kind,
                self.candidate_domain,
            )
        criteria = {
            'choice': self._options(),
            'score': list(self._options()),
        }.get(self.kind)
        return self.env['muk_ai.decision']._free_question(
            f'q{self.id}', self.kind, self.name, criteria
        )

    # ----------------------------------------------------------
    # Compute
    # ----------------------------------------------------------

    @api.depends('field_id')
    def _compute_kind(self) -> None:
        """Derive the type a target field allows, keeping a choice or score on a selection."""
        for record in self:
            if record.field_type == 'boolean':
                record.kind = 'noul'
            elif record.field_type in ('many2one', 'many2many') or not record.kind:
                record.kind = 'choice'

    # ----------------------------------------------------------
    # Constraints
    # ----------------------------------------------------------

    @api.constrains('route_answer', 'field_id', 'kind', 'options', 'candidate_domain')
    def _check_route_answer(self) -> None:
        """Require a route answer the question can give, so a route never stays silent.

        :raise ValidationError: naming the answers the question can give
        """
        for record in self.filtered('route_answer'):
            spec = record._spec()
            answers = (
                ['yes', 'no']
                if spec.kind == 'noul'
                else list(spec.values) or list(spec.questions[spec.field]['criteria'])
            )
            if record.route_answer.strip().casefold() not in map(str.casefold, answers):
                raise ValidationError(
                    self.env._(
                        'Route answer "%(answer)s" is not an answer of "%(question)s". '
                        'Use one of: %(answers)s.',
                        answer=record.route_answer,
                        question=record.name or record.field_id.field_description,
                        answers=', '.join(answers),
                    )
                )

    @api.constrains('name', 'field_id', 'kind', 'options')
    def _check_question(self) -> None:
        """Require a question text without a target field, and options for its type.

        :raise ValidationError: when the question cannot be asked
        """
        for record in self.filtered(lambda question: not question.field_id):
            if not record.name:
                raise ValidationError(
                    self.env._('A question without a target field needs a text.')
                )
            if record.kind != 'noul' and len(record._options()) < 2:
                raise ValidationError(
                    self.env._(
                        'Question "%(question)s" needs at least two options.',
                        question=record.name,
                    )
                )
