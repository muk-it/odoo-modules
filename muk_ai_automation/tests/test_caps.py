from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from odoo import models
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.muk_ai_automation.tools.constants import (
    AGENT_DEFAULT_MAX_COST_EUR,
    AGENT_DEFAULT_MAX_LIFETIME_HOURS,
    AGENT_DEFAULT_MAX_RESUMES,
    AGENT_DEFAULT_MAX_TOTAL_TOKENS,
)


@tagged('post_install', '-at_install', 'muk_ai_automation')
class TestCaps(TransactionCase):
    """Test effective cap propagation from action to session."""

    @classmethod
    def setUpClass(cls) -> None:
        """Set up the provider, agent, and partner model fixtures."""
        super().setUpClass()
        cls.provider = cls.env.ref('muk_ai.provider_openai')
        cls.provider.sudo().api_key = 'test-key'
        cls.env.company.default_ai_provider_id = cls.provider
        cls.agent = cls.env['muk_ai.agent'].create(
            {
                'name': 'Caps Agent',
            }
        )
        cls.partner_model = cls.env['ir.model']._get('res.partner')

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

    def _make_action(self, **vals) -> models.BaseModel:
        """Create an ``ai_agent`` server action with overridable defaults."""
        defaults = {
            'name': 'Caps Action',
            'state': 'ai_agent',
            'model_id': self.partner_model.id,
            'agent_id': self.agent.id,
            'agent_prompt': 'Hello.',
            'agent_dispatch_mode': 'single',
            'agent_record_source': 'domain',
            'agent_record_domain': '[]',
        }
        defaults.update(vals)
        return self.env['ir.actions.server'].create(defaults)

    def _effective_caps(
        self, action: models.BaseModel, session: models.BaseModel
    ) -> dict:
        """Return the session caps, falling back to action-derived defaults."""
        if hasattr(session, '_agent_effective_caps'):
            return session._agent_effective_caps()
        return {
            'max_resumes': (action.agent_max_resumes or AGENT_DEFAULT_MAX_RESUMES),
            'max_lifetime_hours': (
                action.agent_max_lifetime_hours or AGENT_DEFAULT_MAX_LIFETIME_HOURS
            ),
            'max_total_tokens': (
                action.agent_max_total_tokens or AGENT_DEFAULT_MAX_TOTAL_TOKENS
            ),
            'max_cost_eur': (action.agent_max_cost_eur or AGENT_DEFAULT_MAX_COST_EUR),
        }

    def test_agent_max_resumes_propagates(self):
        action = self._make_action(agent_max_resumes=7)
        with self._mock_provider():
            action.run()
        session = self.env['muk_ai.session'].search(
            [('action_server_id', '=', action.id)],
            limit=1,
        )
        self.assertTrue(session)
        caps = self._effective_caps(action, session)
        self.assertEqual(caps['max_resumes'], 7)

    def test_agent_max_total_tokens_propagates(self):
        action = self._make_action(agent_max_total_tokens=12345)
        with self._mock_provider():
            action.run()
        session = self.env['muk_ai.session'].search(
            [('action_server_id', '=', action.id)],
            limit=1,
        )
        self.assertTrue(session)
        caps = self._effective_caps(action, session)
        self.assertEqual(caps['max_total_tokens'], 12345)

    def test_caps_default_to_module_defaults_when_zero(self):
        action = self._make_action(
            agent_max_resumes=0,
            agent_max_lifetime_hours=0,
            agent_max_total_tokens=0,
            agent_max_cost_eur=0.0,
        )
        with self._mock_provider():
            action.run()
        session = self.env['muk_ai.session'].search(
            [('action_server_id', '=', action.id)],
            limit=1,
        )
        self.assertTrue(session)
        caps = self._effective_caps(action, session)
        self.assertEqual(caps['max_resumes'], AGENT_DEFAULT_MAX_RESUMES)
        self.assertEqual(caps['max_lifetime_hours'], AGENT_DEFAULT_MAX_LIFETIME_HOURS)
        self.assertEqual(caps['max_total_tokens'], AGENT_DEFAULT_MAX_TOTAL_TOKENS)
        self.assertEqual(caps['max_cost_eur'], AGENT_DEFAULT_MAX_COST_EUR)
