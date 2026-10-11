from __future__ import annotations

from collections import defaultdict

from odoo import Command, fields, models
from odoo.exceptions import UserError


class IrActionsServer(models.Model):
    """Decide about records with a decision model, and gate agent runs on a decision."""

    _inherit = 'ir.actions.server'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    state = fields.Selection(
        selection_add=[('ai_decision', 'Decide with AI')],
        ondelete={'ai_decision': 'cascade'},
    )

    agent_gate = fields.Text(
        string='Run Only When',
        help=(
            'Yes/no question asked about each record first, e.g. "Does this '
            'ticket still need a reply from us?". Records confidently answered '
            'no are skipped; unsure ones still run.'
        ),
        translate=True,
    )

    agent_gate_min_confidence = fields.Float(
        string='Gate Confidence',
        help='Confidence a "no" needs before a record is skipped.',
        default=0.8,
    )

    decision_question_ids = fields.One2many(
        comodel_name='muk_ai.decision.question',
        inverse_name='action_id',
        string='Questions',
    )

    decision_field_ids = fields.Many2many(
        comodel_name='ir.model.fields',
        relation='muk_ai_decision_action_field_rel',
        column1='action_id',
        column2='field_id',
        string='Reads',
        help=(
            'Fields of the record the decision model reads. Empty, it reads the '
            'name and the text fields.'
        ),
        domain="[('model_id', '=', model_id)]",
    )

    decision_include_message = fields.Boolean(
        string='Read Last Message',
        help='Also read the last email or comment of the record.',
    )

    decision_shadow = fields.Boolean(
        string='Shadow Mode',
        help=(
            'Decide and log only: nothing is written, routed or scheduled. The '
            'log still shows how often the decision matches what people set.'
        ),
    )

    decision_unsure_action_id = fields.Many2one(
        comodel_name='ir.actions.server',
        string='When Unsure',
        help=(
            'Server action run once on all records with an answer below its '
            'confidence, e.g. one that schedules an activity to check them.'
        ),
        domain="[('model_id', '=', model_id), ('id', '!=', id)]",
    )

    decision_log_count = fields.Integer(
        compute='_compute_decision_log_count',
        string='Decisions',
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _decision_states(self, records: models.BaseModel) -> list[str]:
        """Render each record as the text the decision model reads."""
        decision = self.env['muk_ai.decision']
        names = self.decision_field_ids.mapped('name') or (
            decision._default_state_fields(records._name)
        )
        return decision._state_texts(
            records, records.read(names), self.decision_include_message
        )

    def _agent_gate_records(self, records: models.BaseModel) -> models.BaseModel:
        """Return the records the gate does not confidently answer no for."""
        question = {'gate': {'type': 'noul', 'instructions': self.agent_gate}}
        results = self.env['muk_ai.decision'].decide_batch(
            self._decision_states(records),
            question,
            min_confidence=self.agent_gate_min_confidence,
            records=records,
            origin=self.name,
            log_values={'action_id': self.id},
        )
        return records.browse(
            record.id
            for record, result in zip(records, results, strict=True)
            if isinstance(result, UserError)
            or not result['answers']['gate']['confident']
            or result['answers']['gate']['noul'] >= 0.5
        )

    def _decision_outcome(self, answers: dict, specs: list) -> tuple:
        """Return the confident values, the routed actions and whether one is unsure."""
        decision = self.env['muk_ai.decision']
        values, routes, unsure = {}, [], False
        for question, spec in specs:
            labels, line_unsure = decision._answer_labels(
                spec, answers, question.min_confidence
            )
            unsure = unsure or line_unsure
            answer = (question.route_answer or '').strip().casefold()
            if question.route_action_id and answer in map(str.casefold, labels):
                routes.append(question.route_action_id)
            if question.field_id and labels:
                values[spec.field] = (
                    [spec.values[label] for label in labels]
                    if spec.kind == 'tags'
                    else spec.values[labels[0]]
                )
        return values, routes, unsure

    def _run_action_ai_agent_multi(self, eval_context: dict) -> dict | bool:
        """Start the chats only for the records the gate lets through."""
        if self.agent_gate and (records := self._agent_records(eval_context)):
            if not (passed := self._agent_gate_records(records)):
                return False
            eval_context = {**eval_context, 'records': passed}
        return super()._run_action_ai_agent_multi(eval_context)

    def _run_action_ai_decision_multi(self, eval_context: dict) -> dict | bool:
        """Decide about the target records, then write, route and flag the unsure.

        :return: a notification counting the decided, written and unsure records
        """
        records = self._agent_records(eval_context)
        if self.agent_max_records_per_fire > 0:
            records = records[: self.agent_max_records_per_fire]
        if not records:
            return False
        specs = [
            (question, question._spec()) for question in self.decision_question_ids
        ]
        questions = {
            key: q for _line, spec in specs for key, q in spec.questions.items()
        }
        results = self.env['muk_ai.decision'].decide_batch(
            self._decision_states(records),
            questions,
            min_confidence={
                key: line.min_confidence
                for line, spec in specs
                for key in spec.questions
            },
            records=records,
            origin=self.name,
            log_values={'action_id': self.id, 'shadow': self.decision_shadow},
        )
        logs = self.env['muk_ai.decision.log'].sudo()
        routed = defaultdict(records.browse)
        unsure, written = records.browse(), records.browse()
        for record, result in zip(records, results, strict=True):
            if isinstance(result, UserError):
                unsure |= record
                continue
            values, routes, record_unsure = self._decision_outcome(
                result['answers'], specs
            )
            logs.browse(result['log_id']).applied = values
            if record_unsure:
                unsure |= record
            for action in routes:
                routed[action] |= record
            if values and not self.decision_shadow:
                record.write(
                    {
                        name: [Command.link(tag) for tag in value]
                        if isinstance(value, list)
                        else value
                        for name, value in values.items()
                    }
                )
                written |= record
        if unsure and self.decision_unsure_action_id:
            routed[self.decision_unsure_action_id] |= unsure
        if not self.decision_shadow:
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
                'type': 'success',
                'message': self.env._(
                    '%(name)s decided about %(count)s records: %(written)s written, '
                    '%(unsure)s unsure.',
                    name=self.name,
                    count=len(records),
                    written=len(written),
                    unsure=len(unsure),
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

    def _compute_decision_log_count(self) -> None:
        """Count the logged decisions of each action."""
        counts = dict(
            self.env['muk_ai.decision.log']
            .sudo()
            ._read_group([('action_id', 'in', self.ids)], ['action_id'], ['__count'])
        )
        for record in self:
            record.decision_log_count = counts.get(record, 0)
