from __future__ import annotations

import json
import time

from odoo import api
from odoo.exceptions import UserError

from odoo.addons.muk_ai_decision.providers.base import DecisionProviderBase, elapsed_ms

INSTRUCTIONS = (
    'You are a decision model. Read the state and answer every question with '
    'the JSON the schema asks for. Every confidence and probability is a '
    'number between 0 and 1.'
)


def _text(value) -> str:
    """Return ``value`` as prompt text, JSON-encoding anything but a string."""
    return value if isinstance(value, str) else json.dumps(value, default=str)


def _unit(value) -> float:
    """Clamp a reported confidence or probability into ``[0, 1]``."""
    return min(max(float(value or 0.0), 0.0), 1.0)


class LLMDecisionProvider(DecisionProviderBase):
    """Answer decisions with a chat model through its structured output.

    The model reports its own confidence, which is not calibrated like the
    probabilities of a decision model.
    """

    name = 'llm'

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @staticmethod
    def _answer_properties(question: dict) -> dict:
        """Return the JSON schema properties of the answer to one question."""
        kind = question['type']
        if kind == 'choice':
            return {
                'choice': {'type': 'string', 'enum': list(question['criteria'])},
                'confidence': {'type': 'number'},
            }
        if kind == 'score':
            return {'level': {'type': 'integer'}, 'confidence': {'type': 'number'}}
        return {'probability': {'type': 'number'}}

    @classmethod
    def _schema(cls, questions: dict) -> dict:
        """Return the strict JSON schema answering every question once."""

        def strict(properties: dict) -> dict:
            """Wrap ``properties`` into a closed object requiring each of them."""
            return {
                'type': 'object',
                'properties': properties,
                'required': list(properties),
                'additionalProperties': False,
            }

        return strict(
            {
                key: strict(cls._answer_properties(question))
                for key, question in questions.items()
            }
        )

    @staticmethod
    def _prompt(state, questions: dict) -> str:
        """Render the state and the questions with their options as prompt text."""
        lines = ['State:', _text(state), '', 'Questions:']
        for key, question in questions.items():
            kind, criteria = question['type'], question.get('criteria')
            lines.append(f'- {key} ({kind}): {_text(question["instructions"])}')
            if kind == 'choice':
                lines.extend(
                    f'  - "{option}": {_text(text)}' if text else f'  - "{option}"'
                    for option, text in criteria.items()
                )
            elif kind == 'score':
                lines.extend(
                    f'  - level {index}: {_text(text)}'
                    for index, text in enumerate(criteria)
                )
            elif criteria:
                lines.extend(
                    f'  - {answer}: {_text(criteria[answer])}'
                    for answer in ('true', 'false')
                    if criteria.get(answer)
                )
        return '\n'.join(lines)

    @staticmethod
    def _answer(question: dict, raw: dict) -> dict:
        """Map the model's raw answer to one question onto the System One shape."""
        kind = question['type']
        if kind == 'choice':
            if raw['choice'] not in question['criteria']:
                msg = f'unknown option {raw["choice"]!r}'
                raise ValueError(msg)
            return {
                'type': 'choice',
                'choice': raw['choice'],
                'confidence': _unit(raw['confidence']),
            }
        if kind == 'score':
            levels = question['criteria']
            return {
                'type': 'score',
                'score': float(min(max(int(raw['level']), 0), len(levels) - 1)),
                'legend': {str(index): level for index, level in enumerate(levels)},
                'confidence': _unit(raw['confidence']),
            }
        return {'type': 'noul', 'noul': _unit(raw['probability'])}

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    def decide(self, model: str, state, questions: dict) -> dict:
        """Ask the chat model for a structured answer and map it to System One.

        :raise UserError: when the request fails or the answer does not parse
        """
        result = self.provider._request_responses(
            inputs=[
                {'role': 'system', 'content': INSTRUCTIONS},
                {'role': 'user', 'content': self._prompt(state, questions)},
            ],
            text_schema={'name': 'decision', 'schema': self._schema(questions)},
            model=model,
            reasoning_effort='low',
        )
        try:
            raw = json.loads(result['text'])
            answers = {
                key: self._answer(question, raw[key])
                for key, question in questions.items()
            }
        except (ValueError, TypeError, KeyError) as error:
            self.client._raise(error)
        return {'model': model, 'answers': answers, 'usage': result.get('usage')}

    def decide_many(self, model: str, states: list, questions: dict) -> list[tuple]:
        """Ask the chat model about the states concurrently, each on its own cursor.

        A worker thread reads the provider through a cursor of its own, never
        through the one of the calling transaction.
        """
        if len(states) < 2:
            return super().decide_many(model, states, questions)
        env = self.provider.env
        registry, uid, context = env.registry, env.uid, env.context
        provider_id = self.provider.id

        def run(state) -> tuple:
            """Decide about one state, pairing the answer or its error with its duration."""
            started = time.monotonic()
            with registry.cursor() as cr:
                provider = api.Environment(cr, uid, context)['muk_ai.provider']
                adapter = type(self)(provider.browse(provider_id))
                try:
                    outcome = adapter.decide(model, state, questions)
                except UserError as error:
                    outcome = error
            return outcome, elapsed_ms(started)

        return self._run_parallel(run, states)
