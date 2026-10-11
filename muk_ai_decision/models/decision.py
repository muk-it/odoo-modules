from __future__ import annotations

import json

from odoo import api, models
from odoo.exceptions import UserError
from odoo.tools import html2plaintext
from odoo.tools.safe_eval import safe_eval

from odoo.addons.muk_ai_decision.tools.field_question import (
    FIELD_TYPES,
    MAX_CANDIDATES,
    MAX_CHOICES,
    MAX_LEVELS,
    MAX_STATE_FIELDS,
    FieldQuestion,
)


class AIDecision(models.AbstractModel):
    """Answer typed questions about a state with the configured decision models."""

    _name = 'muk_ai.decision'
    _description = 'AI Decision'
    _explanation = (
        'The service that answers typed questions about a text or a record: a '
        'choice, a score or a yes/no probability, each with its confidence. '
        'Use it to classify, rank or triage records with a decision model.'
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _question_error(self, question) -> str | None:
        """Return why the decision API would refuse ``question``, or ``None``."""
        kind = question.get('type') if isinstance(question, dict) else None
        if kind not in ('choice', 'score', 'noul') or not question.get('instructions'):
            return self.env._('needs the type choice, score or noul and instructions')
        criteria = question.get('criteria')
        if kind == 'choice' and not (
            isinstance(criteria, dict) and 2 <= len(criteria) <= MAX_CHOICES
        ):
            return self.env._('needs between 2 and 255 options')
        if kind == 'score' and not (
            isinstance(criteria, list)
            and 2 <= len(criteria) <= MAX_LEVELS
            and len(set(map(str, criteria))) == len(criteria)
        ):
            return self.env._('needs between 2 and 10 distinct levels')
        if kind == 'noul' and not (
            criteria is None
            or (isinstance(criteria, dict) and set(criteria) <= {'true', 'false'})
        ):
            return self.env._('may only describe true and false')
        return None

    @api.model
    def _check_questions(self, questions) -> None:
        """Reject a question set the decision API would refuse.

        :raise UserError: on the first invalid question
        """
        if not isinstance(questions, dict) or not questions:
            raise UserError(self.env._('A decision needs at least one question.'))
        for key, question in questions.items():
            if problem := self._question_error(question):
                raise UserError(
                    self.env._(
                        'Question "%(key)s" %(problem)s.', key=key, problem=problem
                    )
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
            providers.sorted('serves_chat')
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
                self.env._(
                    'Field "%(field)s" cannot be decided: only yes/no, selection, '
                    'many2one and tags fields have a fixed set of values.',
                    field=field_name,
                )
            )
        text = instructions or self.env._('Which %(field)s fits?', field=field.string)
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
                'instructions': self.env._(
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
                self.env._(
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
        """Return the fields a decision reads by default: the name and the text fields."""
        model = self.env[model_name]
        names = [model._rec_name] if model._rec_name in model._fields else []
        names += [
            name
            for name, field in model._fields.items()
            if field.type in ('text', 'html') and field.store and name not in names
        ]
        return names[:MAX_STATE_FIELDS] or ['display_name']

    @api.model
    def _state_texts(
        self, records: models.BaseModel, rows: list, include_message: bool = False
    ) -> list[str]:
        """Render read rows as the JSON a decision model reads, HTML as plain text.

        :param include_message: add the last email or comment of each record
        """
        states = []
        for record, row in zip(records, rows, strict=True):
            state = {
                name: html2plaintext(value or '')
                if records._fields[name].type == 'html'
                else value
                for name, value in row.items()
                if name != 'id'
            }
            if include_message and 'message_ids' in records._fields:
                message = record.message_ids.filtered(
                    lambda message: (
                        message.message_type in ('email', 'comment') and message.body
                    )
                )[:1]
                state['last_message'] = html2plaintext(message.body or '')
            states.append(json.dumps(state, default=str, ensure_ascii=False))
        return states

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    def decide_batch(
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
                self.env._(
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
    def decide(
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
        (result,) = self.decide_batch(
            [state], questions, model, min_confidence, record or None, origin
        )
        if isinstance(result, UserError):
            raise result
        return result
