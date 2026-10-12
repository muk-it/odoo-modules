from __future__ import annotations

from odoo import api, models
from odoo.exceptions import UserError

from odoo.addons.muk_ai_decision.tools.field_question import FieldQuestion
from odoo.addons.muk_mcp.core.tool import mcp_tool
from odoo.addons.muk_mcp.tools.descriptions import (
    domain_field,
    fields_field,
    ids_field,
    model_field,
)
from odoo.addons.muk_mcp.tools.parser import coerce_json_value, normalize_ids

MAX_RECORDS = 100

QUESTION_SCHEMA = {
    'type': 'object',
    'properties': {
        'field': {
            'type': 'string',
            'description': (
                'Field of "model" the question fills: a yes/no, selection, '
                'many2one or tags field. Its values become the options, so no '
                'ids need to be looked up. Omit for a free question.'
            ),
        },
        'key': {
            'type': 'string',
            'description': 'Id the answer comes back under; the field name by default.',
        },
        'type': {
            'type': 'string',
            'enum': ['choice', 'score', 'noul'],
            'description': (
                '"choice" picks one of "options", "score" rates on "levels", '
                '"noul" returns the probability of yes. Derived from "field".'
            ),
        },
        'instructions': {
            'type': 'string',
            'description': 'The question, e.g. "Which team should handle this?".',
        },
        'options': {
            'type': 'array',
            'items': {'type': 'string'},
            'description': 'choice without field: 2 to 255 option names.',
        },
        'levels': {
            'type': 'array',
            'items': {'type': 'string'},
            'description': 'score: 2 to 10 levels, lowest first, e.g. ["Low", "High"].',
        },
        'candidates': {
            'type': 'string',
            'description': (
                'many2one or tags field: JSON domain on the records it may be set '
                'to, when it has more than 50.'
            ),
        },
    },
}


class AIDecisionTool(models.AbstractModel):
    """Expose typed decisions as an MCP tool, about texts or records."""

    _inherit = 'muk_mcp.mixin'

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _decision_specs(
        self, model: str | None, questions: list
    ) -> list[FieldQuestion]:
        """Turn the tool's question list into the questions of the service.

        :raise UserError: on an invalid question, or a field question without model
        """
        decision = self.env['muk_ai.decision']
        specs = []
        for item in coerce_json_value(questions) or []:
            if field := item.get('field'):
                if not model:
                    raise UserError(
                        self.env._('A question with a field needs the model.')
                    )
                specs.append(
                    decision._field_question(
                        model,
                        field,
                        item.get('instructions'),
                        item.get('type'),
                        coerce_json_value(item.get('candidates')),
                    )
                )
                continue
            kind = item.get('type')
            criteria = {
                'choice': dict.fromkeys(item.get('options') or []),
                'score': item.get('levels'),
            }.get(kind)
            specs.append(
                decision._free_question(
                    item.get('key') or f'q{len(specs) + 1}',
                    kind,
                    item.get('instructions'),
                    criteria,
                )
            )
        decision._check_questions(
            {key: q for spec in specs for key, q in spec.questions.items()}
        )
        return specs

    @api.model
    def _decision_groups(
        self, specs: list, targets: list, results: list, min_confidence: float
    ) -> dict:
        """Group the targets by confident answer, with the value a field takes.

        :param targets: the record id or the text index each result belongs to
        :return: the groups and the unsure targets per question, and the errors
        """
        decision = self.env['muk_ai.decision']
        groups = {spec.field: {} for spec in specs}
        unsure = {spec.field: [] for spec in specs}
        errors = []
        for target, result in zip(targets, results, strict=True):
            if isinstance(result, UserError):
                errors.append({'target': target, 'error': str(result)})
                continue
            for spec in specs:
                labels, line_unsure = decision._answer_labels(
                    spec, result['answers'], min_confidence
                )
                if line_unsure:
                    unsure[spec.field].append(target)
                for label in labels:
                    group = groups[spec.field].setdefault(label, {'targets': []})
                    group['targets'].append(target)
                    if label in spec.values:
                        group['value'] = spec.values[label]
        return {
            'groups': groups,
            'unsure': {key: found for key, found in unsure.items() if found},
            'errors': errors,
        }

    @api.model
    def _decision_cost(self, results: list) -> list[dict]:
        """Return what the answered decisions cost, one block per decision model."""
        logs = (
            self.env['muk_ai.decision.log']
            .sudo()
            .browse(result['log_id'] for result in results if isinstance(result, dict))
        )
        return [
            {
                'model_id': model.id,
                'usage': {
                    'input_tokens': sum(answered.mapped('input_tokens')),
                    'output_tokens': sum(answered.mapped('output_tokens')),
                },
                'total': sum(answered.mapped('total_cost')),
                'currency': model.currency,
            }
            for model in logs.model_id
            for answered in [logs.filtered(lambda log: log.model_id == model)]
        ]

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    @mcp_tool(
        name='decide',
        description=(
            'Answer typed questions with a fast decision model instead of judging '
            'the data yourself: is this message spam, which tags fit this ticket, '
            'which team should take it, how urgent is it, does it need a reply. '
            'Decide about "texts" (an email, a message, anything you were given), '
            'about the records "ids" names, or about every record "domain" '
            'selects in one call, each record read as its own text. A question '
            'with "field" takes its options from that field of "model", for texts '
            'too, so no tag or team ids need to be looked up. The result groups the '
            'targets (record ids, or text positions) by confident answer, with the '
            '"value" to write for a field question; answers below "min_confidence" '
            'are listed as unsure. Each call costs money and counts against the turn '
            'budget.'
        ),
        input_schema={
            'type': 'object',
            'properties': {
                'questions': {
                    'type': 'array',
                    'items': QUESTION_SCHEMA,
                    'description': 'The questions, all answered about every target.',
                },
                'texts': {
                    'type': 'array',
                    'items': {'type': 'string'},
                    'description': 'Texts to decide about, each on its own.',
                },
                'model': model_field(),
                'ids': ids_field('decide about'),
                'domain': domain_field(
                    extra_note=" Used when neither 'texts' nor 'ids' is given."
                ),
                'fields': fields_field(
                    example=['name', 'description'],
                    extra_note=(
                        'What the decision model reads per record, as labels and '
                        'readable values; the name and the list columns by default.'
                    ),
                ),
                'limit': {
                    'type': 'integer',
                    'description': 'Records the domain decides about, at most 100.',
                },
                'min_confidence': {
                    'type': 'number',
                    'description': 'Confidence between 0 and 1 an answer must reach.',
                },
            },
            'required': ['questions'],
        },
        category='read',
    )
    def _mcp_decide(
        self,
        questions: list,
        texts: list[str] | None = None,
        model: str | None = None,
        ids=None,
        domain=None,
        fields: list[str] | None = None,
        limit: int = 20,
        min_confidence: float = 0.8,
    ) -> dict:
        """Decide about ``texts``, the records ``ids`` names, or those ``domain`` selects.

        :return: the targets grouped by answer, the unsure ones and the cost
        :raise UserError: on invalid questions, or neither texts nor a model
        """
        decision = self.env['muk_ai.decision']
        specs = self._decision_specs(model, questions)
        keyed = {key: q for spec in specs for key, q in spec.questions.items()}
        records = None
        if texts := coerce_json_value(texts):
            states, targets = list(texts), list(range(len(texts)))
        elif model:
            target = self._resolve_model(model)
            if ids := normalize_ids(coerce_json_value(ids)):
                self._mcp_assert_records_allowed(model, ids)
            records = (
                target.browse(ids)
                if ids
                else target.search(
                    coerce_json_value(self._mcp_apply_domain(model, domain)) or [],
                    limit=min(max(limit, 1), MAX_RECORDS),
                )
            )
            states = decision._state_texts(
                records, fields or decision._default_state_fields(model)
            )
            targets = records.ids
        else:
            raise UserError(self.env._('Pass texts, or a model with ids or a domain.'))
        results = decision._decide_batch(
            states, keyed, min_confidence=min_confidence, records=records, origin='mcp'
        )
        return {
            'decided': len(targets),
            **self._decision_groups(specs, targets, results, min_confidence),
            'cost': self._decision_cost(results),
        }
