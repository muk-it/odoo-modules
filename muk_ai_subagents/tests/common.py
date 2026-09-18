from __future__ import annotations

import json

from odoo import models
from odoo.tests.common import tagged

from odoo.addons.muk_ai.tests.common import AITestCommon


def tool_payload(name: str, arguments: dict, call_id: str, text: str = '') -> dict:
    """Build a provider payload emitting one tool call.

    Plain functions rather than methods, because a tour seeds its run in
    ``setUpClass``, where there is no instance to hang a helper off yet.
    """
    return {
        'text': text,
        'tool_calls': [{'call_id': call_id, 'name': name, 'arguments': arguments}],
        'carry_inputs': [
            {
                'type': 'function_call',
                'name': name,
                'arguments': json.dumps(arguments),
                'call_id': call_id,
            }
        ],
        'usage': {'input_tokens': 4, 'output_tokens': 2},
    }


def text_payload(text: str = 'done') -> dict:
    """Build a provider payload carrying a final assistant message."""
    return {
        'text': text,
        'tool_calls': [],
        'carry_inputs': [
            {'type': 'message', 'content': [{'type': 'output_text', 'text': text}]}
        ],
        'usage': {'input_tokens': 1, 'output_tokens': 1},
    }


def delegate_task(objective: str = 'Find things', **extra) -> dict:
    """Build a delegate task for the worker agent."""
    return {'agent': 'Test Worker', 'objective': objective, **extra}


def delegate_payload(tasks: list[dict], call_id: str = 'd1') -> dict:
    """Build a provider payload calling ``delegate`` with ``tasks``."""
    return tool_payload('delegate', {'tasks': tasks}, call_id)


def ask_payload(question: str, call_id: str) -> dict:
    """Build a provider payload calling ``ask_user``."""
    return tool_payload('ask_user', {'question': question}, call_id)


@tagged('post_install', '-at_install', 'muk_ai_subagents')
class SubagentTestCommon(AITestCommon):
    """Shared agents and provider payload builders for the subagent suites."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.provider.sudo().rate_limit = 0
        agents = cls.env['muk_ai.agent']
        cls.worker = agents.create(
            {
                'name': 'Test Worker',
                'system_prompt': 'You are the worker.',
                'approval_mode': 'ask',
            }
        )
        cls.lead = agents.create(
            {
                'name': 'Test Lead',
                'system_prompt': 'You are the lead.',
                'allow_delegation': True,
                'delegate_agent_ids': [(6, 0, cls.worker.ids)],
            }
        )
        cls.Session = cls.env['muk_ai.session']
        cls.Event = cls.env['muk_ai.session.event']

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _session(
        self, agent: models.Model | None = None, user: models.Model | None = None
    ) -> models.Model:
        """Create a top-level session owned by ``user``, or by the current one."""
        Session = self.Session.with_user(user) if user else self.Session
        return Session.create(
            {'name': 'lead chat', 'agent_id': (agent or self.lead).id}
        )

    def _mixin(self, session: models.Model, call_id: str = 'd1') -> models.Model:
        """Return the MCP mixin bound to ``session`` as a direct delegate call."""
        return self.env['muk_mcp.mixin'].with_context(
            muk_mcp_session_id=session.id, muk_ai_delegate_call_id=call_id
        )

    def _tool_payload(
        self, name: str, arguments: dict, call_id: str, text: str = ''
    ) -> dict:
        """Build a provider payload emitting one tool call."""
        return tool_payload(name, arguments, call_id, text)

    def _text(self, text: str = 'done') -> dict:
        """Build a provider payload carrying a final assistant message."""
        return text_payload(text)

    def _task(self, objective: str = 'Find things', **extra) -> dict:
        """Build a delegate task for the worker agent."""
        return delegate_task(objective, **extra)

    def _delegate_payload(self, tasks: list[dict], call_id: str = 'd1') -> dict:
        """Build a provider payload calling ``delegate`` with ``tasks``."""
        return delegate_payload(tasks, call_id)

    def _ask_payload(self, question: str, call_id: str) -> dict:
        """Build a provider payload calling ``ask_user``."""
        return ask_payload(question, call_id)

    def _park(self, count: int = 2, user: models.Model | None = None) -> models.Model:
        """Return a parent parked on ``count`` subagents that each ask a question."""
        session = self._session(user=user)
        tasks = [self._task(f'Task {index}') for index in range(count)]
        asks = [self._ask_payload(f'Q{index}', f'a{index}') for index in range(count)]
        with self._mock_responses([self._delegate_payload(tasks), *asks]):
            session.start('go')
        return session

    def _delegate_outputs(self, session: models.Model, call_id: str = 'd1') -> list:
        """Return the parsed tool outputs answering the delegate call."""
        return [
            json.loads(item['output'])
            for item in session.conversation or []
            if item.get('type') == 'function_call_output'
            and item.get('call_id') == call_id
        ]

    def _events(self, session: models.Model, kind: str) -> models.Model:
        """Return the persisted events of ``kind`` on ``session``."""
        return self.Event.search(
            [('session_id', '=', session.id), ('kind', '=', kind)], order='sequence'
        )
