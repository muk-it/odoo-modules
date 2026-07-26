from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from odoo import models
from odoo.tests.common import TransactionCase


class AutomationTestCommon(TransactionCase):
    """Shared fixtures for the ``ai_agent`` server-action test suites."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        """Set up the stubbed provider, the agent, and the partner model."""
        super().setUpClass()
        cls.provider = cls.env.ref('muk_ai.provider_openai')
        cls.provider.sudo().write({'api_key': 'test-key', 'rate_limit': 0})
        cls.env.company.default_ai_provider_id = cls.provider
        cls.agent = cls.env['muk_ai.agent'].create({'name': 'Automation Test Agent'})
        cls.partner_model = cls.env['ir.model']._get('res.partner')

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @contextmanager
    def _mock_provider(self, text: str = 'ok') -> Iterator[MagicMock]:
        """Patch the provider request to return a canned response payload."""
        payload = {
            'text': text,
            'tool_calls': [],
            'carry_inputs': [],
            'usage': {'input_tokens': 1, 'output_tokens': 1, 'cached_tokens': 0},
        }

        def fake(self_arg, *args, **kwargs):
            return payload

        with patch.object(
            type(self.provider),
            '_request_responses',
            autospec=True,
            side_effect=fake,
        ) as mock:
            yield mock

    def _action_vals(self, **vals) -> dict:
        """Return the create values of an ``ai_agent`` server action."""
        defaults = {
            'name': 'Agent Action',
            'state': 'ai_agent',
            'model_id': self.partner_model.id,
            'agent_id': self.agent.id,
            'agent_prompt': 'Hello.',
            'agent_dispatch_mode': 'single',
            'agent_record_source': 'domain',
            'agent_record_domain': '[]',
        }
        defaults.update(vals)
        return defaults

    def _make_action(self, **vals) -> models.BaseModel:
        """Create an ``ai_agent`` server action with overridable defaults."""
        return self.env['ir.actions.server'].create(self._action_vals(**vals))

    @classmethod
    def _make_partners(cls, count: int, prefix: str = 'Partner') -> models.BaseModel:
        """Create ``count`` partners named after ``prefix``."""
        return cls.env['res.partner'].create(
            [{'name': '%s %d' % (prefix, index)} for index in range(count)]
        )

    def _partner_field(self, name: str) -> models.BaseModel:
        """Return the ``ir.model.fields`` record of a ``res.partner`` field.

        :param name: the technical field name to look up
        """
        return self.env['ir.model.fields']._get('res.partner', name)

    def _domain_for(self, records: models.BaseModel) -> str:
        """Return a domain string matching ``records`` by id."""
        return "[('id', 'in', %s)]" % str(records.ids)

    def _sessions_of(self, action: models.BaseModel) -> models.BaseModel:
        """Return the sessions spawned by ``action``, oldest first."""
        return self.env['muk_ai.session'].search(
            [('action_server_id', '=', action.id)],
            order='id',
        )
