from __future__ import annotations

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

from odoo.addons.muk_ai_decision.tools.field_question import FIELD_TYPES, FieldQuestion


class AIDecisionQuestion(models.Model):
    """One question a Decide with AI action asks about each record."""

    _name = 'muk_ai.decision.question'
    _description = 'AI Decision Question'
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
            'this ticket?". Optional with a field, which names it.'
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
            ('field', 'Fill a Field'),
            ('choice', 'Own Categories'),
            ('noul', 'Yes/No Check'),
            ('score', 'Score'),
        ],
        string='Goal',
        help=(
            'What the answer does: fill a yes/no, selection, many2one or tags '
            'field, pick one of own categories, check a yes/no question, or rate '
            'on ordered levels.'
        ),
        readonly=False,
        required=True,
        store=True,
    )

    field_scale = fields.Boolean(
        string='Ordered Levels',
        help=(
            'Read the values of the selection field as levels from lowest to '
            'highest, as for a priority, rather than as separate choices.'
        ),
    )

    option_ids = fields.One2many(
        comodel_name='muk_ai.decision.option',
        inverse_name='question_id',
        string='Options',
        help='The categories, or the levels of a score from lowest to highest.',
        copy=True,
    )

    tag_operation = fields.Selection(
        selection=[
            ('add', 'Add'),
            ('set', 'Add and Remove'),
        ],
        string='Operation',
        help=(
            'Add the values that apply, or also remove the candidates that '
            'confidently do not.'
        ),
        default='add',
    )

    candidate_domain = fields.Char(
        string='Candidates',
        help='Filter on the records a many2one or tags field may be set to.',
        default='[]',
    )

    candidate_names = fields.Char(
        compute='_compute_candidate_names',
        string='Candidate Names',
    )

    route_answer = fields.Char(
        string='Route Answer',
        help=(
            'Answer that runs the route action: an option, a level or a tag name, '
            'or "yes" or "no".'
        ),
    )

    route_noul = fields.Selection(
        compute='_compute_route_noul',
        inverse='_inverse_route_noul',
        selection=[
            ('yes', 'Yes'),
            ('no', 'No'),
        ],
        string='When the Answer Is',
    )

    route_action_id = fields.Many2one(
        comodel_name='ir.actions.server',
        string='Run Action',
        help='Server action run once on all records answered with the route answer.',
        domain="[('model_id', '=', model_id), ('id', '!=', action_id)]",
        ondelete='set null',
    )

    unsure_action_id = fields.Many2one(
        comodel_name='ir.actions.server',
        string='When Unsure',
        help=(
            'Server action run once on all records whose answer to this question '
            'stays below its confidence, e.g. one that schedules a check.'
        ),
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
        """Map the label of each option to its description."""
        return {option.name: option.description or None for option in self.option_ids}

    def _fills_field(self) -> bool:
        """Return whether the answer fills the target field."""
        return bool(self.field_id) and self.kind == 'field'

    def _spec(self) -> FieldQuestion:
        """Return the questions this line asks and the value of each answer."""
        if self._fills_field():
            return self.env['muk_ai.decision']._field_question(
                self.action_id.model_name,
                self.field_id.name,
                self.name,
                'score' if self.field_scale else self.kind,
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

    @api.depends('kind', 'field_id', 'candidate_domain')
    def _compute_candidate_names(self) -> None:
        """List the records the candidate domain lets the decision choose from."""
        for record in self:
            if record.kind != 'field' or record.field_type not in (
                'many2one',
                'many2many',
            ):
                record.candidate_names = False
                continue
            field = self.env[record.model_id.model]._fields[record.field_id.name]
            try:
                candidates = self.env['muk_ai.decision']._field_candidates(
                    field, record.candidate_domain
                )
            except (UserError, ValueError) as error:
                record.candidate_names = str(error)
                continue
            record.candidate_names = ', '.join(candidates.mapped('display_name'))

    @api.depends('route_answer')
    def _compute_route_noul(self) -> None:
        """Read a yes or no route answer as a choice."""
        for record in self:
            answer = (record.route_answer or '').strip().casefold()
            record.route_noul = answer if answer in ('yes', 'no') else False

    def _inverse_route_noul(self) -> None:
        """Store the chosen yes or no as the route answer."""
        for record in self:
            record.route_answer = record.route_noul

    @api.depends('field_id')
    def _compute_kind(self) -> None:
        """Derive the goal from the target field."""
        for record in self:
            if record.field_id:
                record.kind = 'field'
            elif not record.kind:
                record.kind = 'choice'

    # ----------------------------------------------------------
    # Constraints
    # ----------------------------------------------------------

    @api.constrains(
        'route_answer', 'field_id', 'kind', 'option_ids', 'candidate_domain'
    )
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

    @api.constrains('name', 'field_id', 'kind', 'option_ids')
    def _check_question(self) -> None:
        """Require a field to fill, else a question text and options for its goal.

        :raise ValidationError: when the question cannot be asked
        """
        for record in self.filtered(lambda question: not question._fills_field()):
            if record.kind == 'field':
                raise ValidationError(
                    self.env._('A question that fills a field needs one.')
                )
            if not record.name:
                raise ValidationError(
                    self.env._('A question without a target field needs a text.')
                )
            for question in record._spec().questions.values():
                if error := self.env['muk_ai.decision']._question_error(question):
                    raise ValidationError(
                        self.env._(
                            'Question "%(question)s" %(error)s.',
                            question=record.name,
                            error=error,
                        )
                    )
