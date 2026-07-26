from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from odoo import models
from odoo.tests.common import TransactionCase


class ScheduleTestCommon(TransactionCase):
    """Shared fixtures for the AI schedule test suites."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        """Set up the stubbed provider, the agent, and the model shortcuts."""
        super().setUpClass()
        cls.provider = cls.env.ref('muk_ai.provider_openai')
        cls.provider.sudo().write({'api_key': 'test-key', 'rate_limit': 0})
        cls.env.company.default_ai_provider_id = cls.provider
        cls.agent = cls.env['muk_ai.agent'].create({'name': 'Schedule Test Agent'})
        cls.partner_model = cls.env['ir.model']._get('res.partner')
        cls.Session = cls.env['muk_ai.session']
        cls.Schedule = cls.env['muk_ai.schedule']
        cls.Mixin = cls.env['muk_mcp.mixin']
        cls.Event = cls.env['muk_ai.session.event']

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

    def _schedule_vals(self, **vals) -> dict:
        """Return the create values of a minimal daily schedule."""
        defaults = {
            'name': 'Test Schedule',
            'agent_id': self.agent.id,
            'prompt': 'Hello.',
            'interval_type': 'days',
            'interval_number': 1,
            'dispatch_mode': 'single',
        }
        defaults.update(vals)
        return defaults

    def _make_schedule(self, **vals) -> models.BaseModel:
        """Create a schedule from the default values overridden by ``vals``."""
        return self.Schedule.create(self._schedule_vals(**vals))

    def _make_session(self, **vals) -> models.BaseModel:
        """Create a session from the default values overridden by ``vals``."""
        defaults = {'name': 'Test Session', 'agent_id': self.agent.id}
        defaults.update(vals)
        return self.Session.create(defaults)

    def _mixin_for(self, session: models.BaseModel) -> models.BaseModel:
        """Return the MCP mixin bound to ``session`` via context."""
        return self.Mixin.with_context(muk_mcp_session_id=session.id)

    @classmethod
    def _make_partners(cls, count: int, prefix: str = 'Partner') -> models.BaseModel:
        """Create ``count`` partners named after ``prefix``."""
        return cls.env['res.partner'].create(
            [{'name': '%s %d' % (prefix, index)} for index in range(count)]
        )

    def _domain_for(self, records: models.BaseModel) -> str:
        """Return a domain string matching ``records`` by id."""
        return "[('id', 'in', %s)]" % str(records.ids)
