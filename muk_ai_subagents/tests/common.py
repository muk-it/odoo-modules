from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta
from unittest.mock import patch

from odoo import fields, models
from odoo.tests import tagged

from odoo.addons.muk_ai.tests.common import AITestCommon

USAGE = {'input_tokens': 10, 'output_tokens': 5}


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
        'usage': dict(USAGE),
    }


def tool_payload(*calls: tuple) -> dict:
    """Build the provider result of a round that calls tools.

    :param calls: ``(name, arguments)`` or ``(name, arguments, call_id)``;
        a missing call id is numbered ``call_1``, ``call_2``, ...
    """
    tool_calls = [
        {
            'call_id': call[2] if len(call) > 2 else f'call_{index}',
            'name': call[0],
            'arguments': call[1],
        }
        for index, call in enumerate(calls, 1)
    ]
    return {
        'text': '',
        'tool_calls': tool_calls,
        'carry_inputs': [
            {
                'type': 'function_call',
                'name': call['name'],
                'arguments': json.dumps(call['arguments']),
                'call_id': call['call_id'],
            }
            for call in tool_calls
        ],
        'usage': dict(USAGE),
    }


@tagged('post_install', '-at_install', 'muk_ai_subagents')
class SubagentCase(AITestCommon):
    """A lead agent that may delegate to a worker agent."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        """Create the worker agent and the lead agent delegating to it."""
        super().setUpClass()
        cls.provider.sudo().rate_limit = 0
        agents = cls.env['muk_ai.agent']
        cls.worker = agents.create(
            {
                'name': 'Worker',
                'description': 'Looks things up.',
                'system_prompt': 'You are the worker.',
                'approval_mode': 'ask',
            }
        )
        cls.lead = agents.create(
            {
                'name': 'Lead',
                'system_prompt': 'You are the lead.',
                'allow_delegation': True,
                'delegate_agent_ids': [(6, 0, cls.worker.ids)],
            }
        )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _session(self, **values) -> models.BaseModel:
        """Create a chat session owned by the current user."""
        return self.env['muk_ai.session'].create({'name': 'Test chat', **values})

    def _lead_chat(self, **values) -> models.BaseModel:
        """Create a chat with the lead agent."""
        return self._session(agent_id=self.lead.id, **values)

    @contextmanager
    def _mock_responses(
        self, payloads: list, repeat_last: bool = False
    ) -> Iterator[list[dict]]:
        """Answer each provider round with the next payload, in order.

        A payload may be a callable taking the request, or an exception to
        raise. Yields every request, its inputs materialized.
        """
        remaining = list(payloads)
        captured = []

        def fake(self_arg, inputs=None, **kwargs) -> dict:
            """Record the request and return the next scripted payload."""
            request = {**kwargs, 'inputs': self_arg._materialize_inputs(inputs)}
            captured.append(request)
            if not remaining:
                msg = 'No more mocked provider responses'
                raise AssertionError(msg)
            if repeat_last and len(remaining) == 1:
                answer = remaining[0]
            else:
                answer = remaining.pop(0)
            if isinstance(answer, Exception):
                raise answer
            return answer(request) if callable(answer) else answer

        with patch.object(
            type(self.provider), '_request_responses', autospec=True, side_effect=fake
        ):
            yield captured

    def _set_params(self, values: dict) -> None:
        """Store config parameters."""
        params = self.env['ir.config_parameter'].sudo()
        for key, value in values.items():
            params.set_param(key, str(value))

    @contextmanager
    def _capture_bus(self) -> Iterator[list[tuple]]:
        """Collect every bus notification as ``(target, type, message)``."""
        captured = []

        def fake(self_arg, target, notification_type, message) -> None:
            """Record the notification instead of queueing it."""
            captured.append((target, notification_type, message))

        with patch.object(
            type(self.env['bus.bus']), '_sendone', autospec=True, side_effect=fake
        ):
            yield captured

    def _backdate(
        self, records: models.BaseModel, delta: timedelta, *names: str
    ) -> None:
        """Move the given datetime columns of ``records`` ``delta`` into the past."""
        records.flush_recordset()
        when = fields.Datetime.now() - delta
        for name in names or ('write_date',):
            self.env.cr.execute(
                f'UPDATE "{records._table}" SET "{name}" = %s WHERE id IN %s',
                [when, tuple(records.ids)],
            )
        records.invalidate_recordset()

    def _events(self, session: models.BaseModel, kind: str | None = None) -> list:
        """Return the session's transcript events, optionally of one kind."""
        events = session.fetch_events(limit=1000)['events']
        return [event for event in events if kind is None or event['kind'] == kind]

    def _outputs_for(self, session: models.BaseModel, call_id: str) -> list:
        """Return the tool outputs the conversation holds for ``call_id``."""
        return [
            item
            for item in session.conversation or []
            if isinstance(item, dict)
            and item.get('type') == 'function_call_output'
            and item.get('call_id') == call_id
        ]

    def _tool_output(self, session: models.BaseModel, call_id: str) -> dict:
        """Return the decoded tool output the conversation holds for ``call_id``."""
        return json.loads(self._outputs_for(session, call_id)[0]['output'])

    @staticmethod
    def _system_prompt(request: dict) -> str:
        """Return the system prompt a provider request carries."""
        return request['inputs'][0]['content'][0]['text']

    @staticmethod
    def _tools(request: dict) -> set[str]:
        """Return the names of the tools a provider request offers the model."""
        return {tool['name'] for tool in request['tools_schema'] or []}

    @staticmethod
    def _delegate(*objectives: str, call_id: str = 'd1') -> dict:
        """Build a provider round delegating one worker task per objective, waiting."""
        tasks = [
            {'agent': 'Worker', 'objective': objective} for objective in objectives
        ]
        return tool_payload(
            ('delegate', {'tasks': tasks, 'background': False}, call_id)
        )

    @staticmethod
    def _ask(question: str, call_id: str) -> dict:
        """Build a provider round asking the user a question."""
        return tool_payload(('ask_user', {'question': question}, call_id))

    def _park(self, count: int = 2) -> models.BaseModel:
        """Return a lead chat waiting on ``count`` subagents that each asked a question."""
        chat = self._lead_chat()
        objectives = [f'Task {index}' for index in range(count)]
        asks = [self._ask(f'Q{index}', f'a{index}') for index in range(count)]
        with self._mock_responses([self._delegate(*objectives), *asks]):
            chat.start('go')
        return chat

    def _reports(self, chat: models.BaseModel, call_id: str = 'd1') -> list[dict]:
        """Return the results the delegate call answered the lead with."""
        return self._tool_output(chat, call_id)['results']
