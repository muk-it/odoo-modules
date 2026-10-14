from __future__ import annotations

import json

from lxml import etree

from odoo import _, api, models
from odoo.exceptions import UserError
from odoo.tools import html2plaintext
from odoo.tools.safe_eval import safe_eval

from odoo.addons.muk_ai_decision.providers import REGISTRY
from odoo.addons.muk_ai_decision.tools.field_question import (
    FIELD_TYPES,
    MAX_CANDIDATES,
    MAX_CHOICES,
    MAX_LEVELS,
    MAX_VALUE_CHARS,
    FieldQuestion,
)


class AIDecision(models.AbstractModel):
    """Answer typed questions about a state with the configured decision models."""

    _name = 'muk_ai.decision'
    _description = 'AI Decision'

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _question_error(self, question) -> str | None:
        """Return why the decision API would refuse ``question``, or ``None``."""
        kind = question.get('type') if isinstance(question, dict) else None
        if kind not in ('choice', 'score', 'noul') or not question.get('instructions'):
            return _('needs the type choice, score or noul and instructions')
        criteria = question.get('criteria')
        if kind == 'choice' and not (
            isinstance(criteria, dict) and 2 <= len(criteria) <= MAX_CHOICES
        ):
            return _('needs between 2 and 255 options')
        if kind == 'score' and not (
            isinstance(criteria, list)
            and 2 <= len(criteria) <= MAX_LEVELS
            and len(set(map(str, criteria))) == len(criteria)
        ):
            return _('needs between 2 and 10 distinct levels')
        if kind == 'noul' and not (
            criteria is None
            or (isinstance(criteria, dict) and set(criteria) <= {'true', 'false'})
        ):
            return _('may only describe true and false')
        return None

    @api.model
    def _check_questions(self, questions) -> None:
        """Reject a question set the decision API would refuse.

        :raise UserError: on the first invalid question
        """
        if not isinstance(questions, dict) or not questions:
            raise UserError(_('A decision needs at least one question.'))
        for key, question in questions.items():
            if problem := self._question_error(question):
                raise UserError(
                    _('Question "%(key)s" %(problem)s.', key=key, problem=problem)
                )

    @api.model
    def _candidates(self, model: models.BaseModel | None) -> models.BaseModel:
        """Return the decision models to try: the pinned one, else every default.

        Decision providers lead, the chat providers follow, each in list order.
        """
        if model:
            return model
        providers = self.env['muk_ai.provider'].search([('active', '=', True)])
        return (
            providers.sorted(lambda provider: provider.name not in REGISTRY)
            .filtered(lambda provider: provider._can_serve())
            .mapped(lambda provider: provider._default_model('decision'))
        )

    @api.model
    def _confidence(self, answer: dict) -> float:
        """Return the confidence of one answer, a yes/no as its likelier side."""
        if answer.get('type') == 'noul':
            return max(answer['noul'], 1.0 - answer['noul'])
        return answer.get('confidence') or 0.0

    @api.model
    def _flag_confident(self, answers: dict, min_confidence: float | dict) -> dict:
        """Flag each answer ``confident`` when it reaches its minimum confidence.

        :param min_confidence: one minimum for all, or one per question key
        """

        def minimum(key: str) -> float:
            """Return the minimum confidence of the question ``key``."""
            if isinstance(min_confidence, dict):
                return min_confidence.get(key, 0.0)
            return min_confidence

        return {
            key: {**answer, 'confident': self._confidence(answer) >= minimum(key)}
            for key, answer in answers.items()
        }

    @api.model
    def _field_question(
        self,
        model_name: str,
        field_name: str,
        instructions: str | None = None,
        kind: str | None = None,
        domain: str | list | None = None,
    ) -> FieldQuestion:
        """Build the questions that fill a field from the values it allows.

        A tags field asks one yes/no question per candidate tag.
        :raise UserError: when the field has no fixed set of values or too many
        """
        field = self.env[model_name]._fields.get(field_name)
        if not field or field.type not in FIELD_TYPES:
            raise UserError(
                _(
                    'Field "%(field)s" cannot be decided: only yes/no, selection, '
                    'many2one and tags fields have a fixed set of values.',
                    field=field_name,
                )
            )
        text = instructions or _('Which %(field)s fits?', field=field.string)
        if field.type == 'boolean':
            question = {'type': 'noul', 'instructions': instructions or field.string}
            values = {'yes': True, 'no': False}
            return FieldQuestion(field_name, 'noul', {field_name: question}, values)
        if field.type == 'selection':
            labels = self._unique_labels(field._description_selection(self.env))
            if kind == 'score':
                question = {
                    'type': 'score',
                    'instructions': text,
                    'criteria': list(labels),
                }
                return FieldQuestion(
                    field_name, 'score', {field_name: question}, labels
                )
            return self._choice_question(field_name, text, labels)
        candidates = self._field_candidates(field, domain)
        if field.type == 'many2one':
            labels = self._unique_labels(
                [(record.id, record.display_name) for record in candidates]
            )
            return self._choice_question(field_name, text, labels)
        labels = self._unique_labels(
            [(record.id, record.display_name) for record in candidates]
        )
        questions = {
            f'{field_name}:{tag_id}': {
                'type': 'noul',
                'instructions': _(
                    '%(question)s Does "%(tag)s" apply?',
                    question=instructions or field.string,
                    tag=label,
                ),
            }
            for label, tag_id in labels.items()
        }
        return FieldQuestion(field_name, 'tags', questions, labels)

    @api.model
    def _choice_question(
        self, field_name: str, text: str, labels: dict
    ) -> FieldQuestion:
        """Build the choice question picking one of ``labels`` for a field."""
        question = {
            'type': 'choice',
            'instructions': text,
            'criteria': dict.fromkeys(labels),
        }
        return FieldQuestion(field_name, 'choice', {field_name: question}, labels)

    @api.model
    def _free_question(
        self, key: str, kind: str, instructions: str, criteria: dict | list | None
    ) -> FieldQuestion:
        """Build a question that fills no field, answered by its own labels."""
        question = {'type': kind, 'instructions': instructions}
        if criteria is not None:
            question['criteria'] = criteria
        return FieldQuestion(key, kind, {key: question}, {})

    @api.model
    def _unique_labels(self, pairs: list) -> dict:
        """Map each label to its value, suffixing a repeated label with its value."""
        labels = {}
        for value, label in pairs:
            labels[label if label not in labels else f'{label} ({value})'] = value
        return labels

    @api.model
    def _field_candidates(self, field, domain: str | list | None) -> models.BaseModel:
        """Return the records a relational field may be decided to.

        :raise UserError: when fewer than two or more than fifty records qualify
        """
        if isinstance(domain, str):
            domain = safe_eval(domain or '[]', {'env': self.env})
        candidates = self.env[field.comodel_name].search(
            domain or [], limit=MAX_CANDIDATES + 1
        )
        if not 2 <= len(candidates) <= MAX_CANDIDATES:
            raise UserError(
                _(
                    'Field "%(field)s" needs between 2 and 50 candidate records to '
                    'decide between; narrow them with a domain.',
                    field=field.name,
                )
            )
        return candidates

    @api.model
    def _answer_labels(
        self, question: FieldQuestion, answers: dict, min_confidence: float
    ) -> tuple[list[str], bool]:
        """Return the labels of the confident answers, and whether one was unsure.

        A yes/no answers "yes" or "no", a tags field the names of its yes tags.
        """
        if question.kind == 'tags':
            labels, unsure = [], False
            for label, tag_id in question.values.items():
                answer = answers[f'{question.field}:{tag_id}']
                if self._confidence(answer) < min_confidence:
                    unsure = True
                elif answer['noul'] >= 0.5:
                    labels.append(label)
            return labels, unsure
        answer = answers[question.field]
        if self._confidence(answer) < min_confidence:
            return [], True
        if question.kind == 'noul':
            return ['yes' if answer['noul'] >= 0.5 else 'no'], False
        if question.kind == 'score':
            criteria = question.questions[question.field]['criteria']
            return [criteria[round(answer['score'])]], False
        return [answer['choice']], False

    @api.model
    def _default_state_fields(self, model_name: str) -> list[str]:
        """Return the fields a decision reads by default: the name and the list columns."""
        model = self.env[model_name]
        arch = etree.fromstring(model.get_view(view_type='tree')['arch'])
        names = [model._rec_name] if model._rec_name in model._fields else []
        names += [
            node.get('name')
            for node in arch.iter('field')
            if node.get('name') in model._fields
            and node.get('name') not in names
            and node.get('column_invisible') not in ('1', 'True')
            and node.get('optional') != 'hide'
            and model._fields[node.get('name')].type not in ('binary', 'one2many')
        ]
        return names or ['display_name']

    @api.model
    def _record_text(
        self, records: models.BaseModel, names: list[str] | None = None
    ) -> str:
        """Render ``records`` one per line as the labelled fields a decision reads."""
        return '\n'.join(
            self._state_texts(
                records, names or self._default_state_fields(records._name)
            )
        )

    @api.model
    def _display_value(
        self, record: models.BaseModel, name: str
    ) -> str | int | float | bool:
        """Return the value of a field as a person reads it, a long text cut short."""
        field, value = record._fields[name], record[name]
        if field.type in ('boolean', 'integer', 'float', 'monetary'):
            return value
        if field.type in ('many2one', 'one2many', 'many2many'):
            text = ', '.join(value.mapped('display_name'))
        elif field.type == 'selection':
            text = dict(field._description_selection(self.env)).get(value) or ''
        elif field.type == 'html':
            text = html2plaintext(value or '')
        else:
            text = str(value or '')
        return text[:MAX_VALUE_CHARS]

    @api.model
    def _state_texts(
        self,
        records: models.BaseModel,
        names: list[str],
        message_count: int = 0,
        external_only: bool = False,
    ) -> list[str]:
        """Render each record as JSON of the labels and readable values of its fields.

        :param message_count: add that many of the last emails and comments
        :param external_only: skip internal notes among them
        """
        if unknown := [name for name in names if name not in records._fields]:
            raise UserError(
                _(
                    'Unknown fields of %(model)s: %(fields)s',
                    model=records._name,
                    fields=', '.join(unknown),
                )
            )
        labels = {}
        for name in names:
            label = records._fields[name]._description_string(self.env)
            labels[name] = f'{label} ({name})' if label in labels.values() else label
        states = []
        for record in records:
            state = {
                label: self._display_value(record, name)
                for name, label in labels.items()
            }
            if message_count and 'message_ids' in records._fields:
                messages = record.message_ids.filtered(
                    lambda message: (
                        message.message_type in ('email', 'comment')
                        and message.body
                        and not (external_only and message.subtype_id.internal)
                    )
                )[:message_count]
                state[_('Last Messages')] = [
                    f'{message.author_id.display_name or message.email_from} '
                    f'({message.date:%Y-%m-%d}): '
                    f'{html2plaintext(message.body)[:MAX_VALUE_CHARS]}'
                    for message in messages
                ]
            states.append(json.dumps(state, default=str, ensure_ascii=False))
        return states

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    def _decide_batch(
        self,
        states: list,
        questions: dict,
        model: models.BaseModel | None = None,
        min_confidence: float | dict = 0.0,
        records: models.BaseModel | None = None,
        origin: str | None = None,
        log_values: dict | None = None,
    ) -> list:
        """Answer typed ``questions`` about each state at once and log every attempt.

        A pinned ``model`` is the only one asked, else each provider's default
        decision model in list order, the next taking the states the last failed.
        :raise UserError: on invalid questions or when no model is usable
        """
        self._check_questions(questions)
        if not (candidates := self._candidates(model)):
            raise UserError(
                _(
                    'No decision model is available. Set a Default Decision Model '
                    'on a provider that has an API key.'
                )
            )
        logs = self.env['muk_ai.decision.log'].sudo()
        records = records or [None] * len(states)
        results, pending = [None] * len(states), list(range(len(states)))
        for candidate in candidates:
            outcomes = candidate.provider_id._get_decision_client().decide_many(
                candidate.technical_name,
                [states[index] for index in pending],
                questions,
            )
            failed = []
            for index, (outcome, duration) in zip(pending, outcomes, strict=True):
                record = records[index]
                values = {
                    **(log_values or {}),
                    'model_id': candidate.id,
                    'origin': origin,
                    'res_model': record._name if record else False,
                    'res_id': record.id if record else False,
                    'questions': questions,
                    'state_payload': states[index],
                    'duration': duration,
                }
                if isinstance(outcome, UserError):
                    logs.create({**values, 'error': str(outcome)})
                    results[index] = outcome
                    failed.append(index)
                    continue
                usage = outcome.get('usage') or {}
                answers = self._flag_confident(outcome['answers'], min_confidence)
                log = logs.create(
                    {
                        **values,
                        'served_model': outcome.get('model')
                        or candidate.technical_name,
                        'answers': answers,
                        'confident': all(
                            answer['confident'] for answer in answers.values()
                        ),
                        'input_tokens': usage.get('input_tokens') or 0,
                        'output_tokens': usage.get('output_tokens') or 0,
                        'total_cost': candidate._compute_usage_cost(usage)[
                            'total_cost'
                        ],
                        'currency': candidate.currency,
                    }
                )
                results[index] = {
                    'model': log.served_model,
                    'answers': answers,
                    'log_id': log.id,
                }
            if not (pending := failed):
                break
        return results

    @api.model
    def _decide(
        self,
        state,
        questions: dict,
        model: models.BaseModel | None = None,
        min_confidence: float = 0.0,
        record: models.BaseModel | None = None,
        origin: str | None = None,
    ) -> dict:
        """Answer typed ``questions`` about ``state`` and log the decision.

        :return: the served ``model``, the ``answers`` and the ``log_id``
        :raise UserError: on invalid questions, no usable model, or when all fail
        """
        (result,) = self._decide_batch(
            [state], questions, model, min_confidence, record or None, origin
        )
        if isinstance(result, UserError):
            raise result
        return result
