from __future__ import annotations

import json

from odoo import models

from odoo.addons.muk_ai.tests.common import AITestCommon, tool_payload


class SubagentCase(AITestCommon):
    """A lead agent that may delegate to a worker agent."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        """Create the worker agent and the lead agent delegating to it."""
        super().setUpClass()
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

    def _lead_chat(self, **values) -> models.BaseModel:
        """Create a chat with the lead agent."""
        return self._session(agent_id=self.lead.id, **values)

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
        return json.loads(self._outputs_for(chat, call_id)[0]['output'])['results']
