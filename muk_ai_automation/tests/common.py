from __future__ import annotations

import json

from odoo import models

from odoo.addons.muk_ai.tests.common import AITestCommon, text_payload


class AutomationTestCommon(AITestCommon):
    """An agent, partners to run it on and helpers to run ``ai_agent`` actions."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        """Create the agent and three partners."""
        super().setUpClass()
        cls.agent = cls.env['muk_ai.agent'].create({'name': 'Automation Agent'})
        cls.partners = cls.env['res.partner'].create(
            [{'name': f'Partner {index}'} for index in range(3)]
        )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

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
        return result, [json.dumps(request['inputs']) for request in sent]

    def _sessions_of(self, action: models.BaseModel) -> models.BaseModel:
        """Return the chats the action's stat button lists, oldest first."""
        domain = action.action_open_agent_sessions()['domain']
        return self.env['muk_ai.session'].search(domain, order='id')
