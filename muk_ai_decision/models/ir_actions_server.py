from __future__ import annotations

import json
from collections import defaultdict

from odoo import Command, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import html2plaintext
from odoo.tools.safe_eval import safe_eval, test_python_expr

from odoo.addons.muk_ai_automation.tools.dispatch import _resolve_records
from odoo.addons.muk_ai_decision.tools.web_fetch import web_fetch


class IrActionsServer(models.Model):
    """Decide about records with a decision model."""

    _inherit = 'ir.actions.server'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    state = fields.Selection(
        selection_add=[('ai_decision', 'Decide with AI')],
        ondelete={'ai_decision': 'cascade'},
    )

    allowed_states = fields.Json(
        compute='_compute_ai_allowed_states',
    )

    decision_question_ids = fields.One2many(
        comodel_name='muk_ai.decision.question',
        inverse_name='action_id',
        string='Questions',
        copy=True,
    )

    decision_field_ids = fields.Many2many(
        comodel_name='ir.model.fields',
        compute='_compute_decision_field_ids',
        relation='muk_ai_decision_action_field_rel',
        column1='action_id',
        column2='field_id',
        string='Reads',
        help=(
            'Fields of the record the decision model reads, each with its label '
            'and readable value, preset to the name and the list columns.'
        ),
        readonly=False,
        store=True,
        domain="[('model_id', '=', model_id), ('ttype', 'not in', ['binary', 'one2many'])]",
    )

    decision_input_source = fields.Selection(
        selection=[
            ('fields', 'Fields'),
            ('code', 'Python Code'),
        ],
        string='Input',
        help='Read the chosen fields, or the text Python code builds for each record.',
        default='fields',
    )

    decision_input_code = fields.Text(
        compute='_compute_decision_input_code',
        string='Input Code',
        help=(
            'Python code assigning the text the decision model reads to "text", '
            'with record, env and html2plaintext.'
        ),
        readonly=False,
        store=True,
    )

    decision_preview_ref = fields.Reference(
        compute='_compute_decision_preview_ref',
        selection='_selection_target_model',
        string='Preview Record',
        help='Record whose input the preview shows.',
        readonly=False,
    )

    decision_preview = fields.Text(
        compute='_compute_decision_preview',
        string='Preview',
    )

    decision_message_count = fields.Integer(
        string='Read Last Messages',
        help='How many of the last emails and comments of the record to read.',
    )

    decision_message_external = fields.Boolean(
        string='External Only',
        help='Skip internal notes, read only the messages sent or received.',
    )

    decision_log_count = fields.Integer(
        compute='_compute_decision_log_count',
        string='Decisions',
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _decision_states(self, records: models.BaseModel) -> list[str | None]:
        """Render each record as the text the decision model reads, ``None`` for none."""
        decision = self.env['muk_ai.decision']
        if self.decision_input_source == 'code':
            states = []
            for record in records:
                scope = {
                    'record': record,
                    'env': self.env,
                    'html2plaintext': html2plaintext,
                    'web_fetch': web_fetch,
                    'record_text': decision._record_text,
                }
                safe_eval(self.decision_input_code or '', scope, mode='exec')
                states.append(str(scope['text']) if scope.get('text') else None)
            return states
        return decision._state_texts(
            records,
            self.decision_field_ids.mapped('name')
            or decision._default_state_fields(records._name),
            self.decision_message_count,
            self.decision_message_external,
        )

    def _decision_pending(
        self, records: models.BaseModel, states: list, questions: dict
    ) -> tuple[models.BaseModel, list[str]]:
        """Keep the records with an input and questions not yet decided by this action."""
        logs = self.env['muk_ai.decision.log'].sudo()
        last = logs.browse(
            log_id
            for _res_id, log_id in logs._read_group(
                [
                    ('action_id', '=', self.id),
                    ('res_model', '=', records._name),
                    ('res_id', 'in', records.ids),
                    ('error', '=', False),
                ],
                ['res_id'],
                ['id:max'],
            )
        )
        questions = json.loads(json.dumps(questions))
        decided = {
            (log.res_id, log.state_payload)
            for log in last
            if log.questions == questions
        }
        pending = [
            (record, state)
            for record, state in zip(records, states, strict=True)
            if state and (record.id, state) not in decided
        ]
        return (
            records.browse(record.id for record, _state in pending),
            [state for _record, state in pending],
        )

    def _decision_outcome(self, answers: dict, specs: list) -> tuple:
        """Return the values to write and their answers, the routes and if one is unsure."""
        decision = self.env['muk_ai.decision']
        values, applied, routes, unsure = {}, {}, [], False
        for question, spec in specs:
            labels, line_unsure = decision._answer_labels(
                spec, answers, question.min_confidence
            )
            unsure = unsure or line_unsure
            if line_unsure and question.unsure_action_id:
                routes.append(question.unsure_action_id)
            routes += [
                option.action_id
                for option in question.option_ids.filtered('action_id')
                if option.name.casefold() in map(str.casefold, labels)
            ]
            answer = (question.route_answer or '').strip().casefold()
            if question.route_action_id and answer in map(str.casefold, labels):
                routes.append(question.route_action_id)
            if spec.kind == 'tags':
                removed = [
                    label
                    for label, tag_id in spec.values.items()
                    if question.tag_operation == 'set'
                    and label not in labels
                    and decision._confidence(answers[f'{spec.field}:{tag_id}'])
                    >= question.min_confidence
                ]
                if labels or removed:
                    applied[spec.field] = {'add': labels, 'remove': removed}
                    values[spec.field] = [
                        Command.link(spec.values[label]) for label in labels
                    ] + [Command.unlink(spec.values[label]) for label in removed]
            elif question._fills_field() and labels:
                applied[spec.field] = labels[0]
                values[spec.field] = spec.values[labels[0]]
        return values, applied, routes, unsure

    def _run_action_ai_decision_multi(self, eval_context: dict) -> dict | bool:
        """Decide about the target records, then write, route and flag the unsure.

        :return: a notification counting the decided, written, unsure and skipped
            records
        """
        records = _resolve_records(self, eval_context)
        if self.agent_max_records_per_fire > 0:
            records = records[: self.agent_max_records_per_fire]
        if not records:
            return False
        targeted = len(records)
        try:
            specs = [
                (question, question._spec()) for question in self.decision_question_ids
            ]
            questions = {
                key: q for _line, spec in specs for key, q in spec.questions.items()
            }
            records, states = self._decision_pending(
                records, self._decision_states(records), questions
            )
            results = records.ids and self.env['muk_ai.decision']._decide_batch(
                states,
                questions,
                min_confidence={
                    key: line.min_confidence
                    for line, spec in specs
                    for key in spec.questions
                },
                records=records,
                origin=self.name,
                log_values={'action_id': self.id},
            )
        except (UserError, ValueError) as error:
            results = [UserError(str(error))] * len(records)
        errors = sorted(
            {str(result) for result in results if isinstance(result, UserError)}
        )
        logs = self.env['muk_ai.decision.log'].sudo()
        routed = defaultdict(records.browse)
        unsure, written = records.browse(), records.browse()
        for record, result in zip(records, results, strict=True):
            if isinstance(result, UserError):
                unsure |= record
                for action in self.decision_question_ids.unsure_action_id:
                    routed[action] |= record
                continue
            values, applied, routes, record_unsure = self._decision_outcome(
                result['answers'], specs
            )
            logs.browse(result['log_id']).applied = applied
            if record_unsure:
                unsure |= record
            for action in routes:
                routed[action] |= record
            if values:
                record.write(values)
                written |= record
        for action, matched in routed.items():
            action.with_context(
                active_model=matched._name,
                active_ids=matched.ids,
                active_id=matched[:1].id,
            ).run()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'warning' if errors else 'success',
                'message': '\n'.join(
                    [
                        self.env._(
                            '%(name)s decided about %(count)s records: %(written)s '
                            'written, %(unsure)s unsure, %(skipped)s skipped without '
                            'new input.',
                            name=self.name,
                            count=len(records),
                            written=len(written),
                            unsure=len(unsure),
                            skipped=targeted - len(records),
                        ),
                        *errors,
                    ]
                ),
                'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
            },
        }

    # ----------------------------------------------------------
    # Actions
    # ----------------------------------------------------------

    def action_open_decision_logs(self) -> dict:
        """Open the decisions this action took."""
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'muk_ai_decision.action_muk_ai_decision_log'
        )
        return {**action, 'domain': [('action_id', '=', self.id)], 'context': {}}

    # ----------------------------------------------------------
    # Compute
    # ----------------------------------------------------------

    @api.depends_context('ai_steps', 'default_use_in_ai')
    def _compute_ai_allowed_states(self) -> None:
        """Offer only the AI steps to the actions of an AI automation rule."""
        self._compute_allowed_states()
        if self.env.context.get('ai_steps'):
            self.allowed_states = ['ai_decision', 'ai_agent']

    @api.depends('model_id', 'state')
    def _compute_decision_field_ids(self) -> None:
        """Preset the fields a decision reads to the name and the list columns."""
        decision = self.env['muk_ai.decision']
        for action in self.filtered(
            lambda action: action.state == 'ai_decision' and action.model_id
        ):
            action.decision_field_ids = self.env['ir.model.fields'].search(
                [
                    ('model', '=', action.model_id.model),
                    (
                        'name',
                        'in',
                        decision._default_state_fields(action.model_id.model),
                    ),
                ]
            )

    def _compute_decision_log_count(self) -> None:
        """Count the logged decisions of each action."""
        counts = dict(
            self.env['muk_ai.decision.log']
            .sudo()
            ._read_group([('action_id', 'in', self.ids)], ['action_id'], ['__count'])
        )
        for record in self:
            record.decision_log_count = counts.get(record, 0)

    @api.depends('decision_input_source')
    def _compute_decision_input_code(self) -> None:
        """Start empty input code with the display name of the record."""
        for action in self.filtered(
            lambda action: (
                action.decision_input_source == 'code'
                and not action.decision_input_code
            )
        ):
            action.decision_input_code = 'text = record.display_name'

    @api.depends('model_id', 'state')
    def _compute_decision_preview_ref(self) -> None:
        """Preview the input of the first record of the model of a decision."""
        for action in self:
            record = (
                action.state == 'ai_decision'
                and action.model_id
                and self.env[action.model_name].search([], limit=1)
            )
            action.decision_preview_ref = record and f'{record._name},{record.id}'

    @api.depends(
        'decision_preview_ref',
        'decision_input_source',
        'decision_input_code',
        'decision_field_ids',
        'decision_message_count',
        'decision_message_external',
    )
    def _compute_decision_preview(self) -> None:
        """Show the input the decision model reads for the preview record."""
        for action in self:
            record = action.decision_preview_ref
            if (
                action.state != 'ai_decision'
                or not record
                or record._name != action.model_name
            ):
                action.decision_preview = False
                continue
            try:
                state = action._decision_states(record)[0]
            except (UserError, ValueError) as error:
                action.decision_preview = str(error)
                continue
            if not state:
                action.decision_preview = self.env._(
                    'The input code assigns no text, so the record is skipped.'
                )
                continue
            try:
                action.decision_preview = json.dumps(
                    json.loads(state), indent=2, ensure_ascii=False
                )
            except ValueError:
                action.decision_preview = state

    # ----------------------------------------------------------
    # Constraints
    # ----------------------------------------------------------

    @api.constrains('decision_input_code')
    def _check_decision_input_code(self) -> None:
        """Refuse input code that is not valid Python.

        :raise ValidationError: when the code does not compile
        """
        for action in self.sudo().filtered('decision_input_code'):
            if message := test_python_expr(
                expr=action.decision_input_code.strip(), mode='exec'
            ):
                raise ValidationError(message)
