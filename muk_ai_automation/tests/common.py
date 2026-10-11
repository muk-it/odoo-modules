from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import patch

from odoo import models

from odoo.addons.muk_ai.tests.common import AITestCommon


def text_payload(text: str = 'ok') -> dict:
    """Build the provider result of a round that answers with plain text."""
    return {
        'text': text,
        'tool_calls': [],
        'carry_inputs': [
            {
                'type': 'message',
                'role': 'assistant',
                'content': [{'type': 'output_text', 'text': text}],
            }
        ],
        'usage': {'input_tokens': 3, 'output_tokens': 1},
    }


def tool_payload(name: str, arguments: dict) -> dict:
    """Build the provider result of a round that calls one tool."""
    return {
        'text': '',
        'tool_calls': [{'call_id': 'call_1', 'name': name, 'arguments': arguments}],
        'carry_inputs': [
            {
                'type': 'function_call',
                'name': name,
                'arguments': json.dumps(arguments),
                'call_id': 'call_1',
            }
        ],
        'usage': {'input_tokens': 4, 'output_tokens': 2},
    }


class AutomationTestCommon(AITestCommon):
    """An agent, partners to run it on and helpers to run ``ai_agent`` actions."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        """Create the agent and three partners."""
        super().setUpClass()
        cls.provider.sudo().rate_limit = 0
        cls.agent = cls.env['muk_ai.agent'].create({'name': 'Automation Agent'})
        cls.partners = cls.env['res.partner'].create(
            [{'name': f'Partner {index}'} for index in range(3)]
        )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @contextmanager
    def _mock_responses(
        self, payloads: list[dict], repeat_last: bool = False
    ) -> Iterator[list[dict]]:
        """Answer each provider round with the next payload, in order.

        Yields the keyword arguments of every request, ``inputs`` included.
        """
        remaining = list(payloads)
        captured = []

        def fake(self_arg, inputs=None, **kwargs) -> dict:
            """Record the request and return the next scripted payload."""
            captured.append({**kwargs, 'inputs': inputs})
            if not remaining:
                msg = 'No more mocked provider responses'
                raise AssertionError(msg)
            if repeat_last and len(remaining) == 1:
                return remaining[0]
            return remaining.pop(0)

        with patch.object(
            type(self.provider), '_request_responses', autospec=True, side_effect=fake
        ):
            yield captured

    def _domain_for(self, records: models.BaseModel) -> str:
        """Return a domain string matching ``records`` by id."""
        return f"[('id', 'in', {records.ids})]"

    def _make_action(self, **values) -> models.BaseModel:
        """Create an ``ai_agent`` action on partners running over ``self.partners``."""
        return self.env['ir.actions.server'].create(
            {
                'name': 'Agent Action',
                'state': 'ai_agent',
                'model_id': self.env['ir.model']._get_id('res.partner'),
                'agent_id': self.agent.id,
                'agent_prompt': 'Hello.',
                'agent_record_domain': self._domain_for(self.partners),
                **values,
            }
        )

    def _run(
        self, action: models.BaseModel, answer: str = 'done', **context
    ) -> tuple[dict | bool, list[str]]:
        """Run ``action`` against a provider answering ``answer``.

        :return: the result of the run and each request sent, as JSON text
        """
        with self._mock_responses([text_payload(answer)], repeat_last=True) as sent:
            result = action.with_context(**context).run()
        return result, [json.dumps(request['inputs'], default=str) for request in sent]

    def _sessions_of(self, action: models.BaseModel) -> models.BaseModel:
        """Return the chats the action's stat button lists, oldest first."""
        domain = action.action_open_agent_sessions()['domain']
        return self.env['muk_ai.session'].search(domain, order='id')
