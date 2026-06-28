from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from odoo import models
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.muk_ai_automation.tools.dispatch import fire_action


@tagged('post_install', '-at_install', 'muk_ai_automation')
class TestChainStrategy(TransactionCase):
    """Test per-record chaining of sessions across repeated fires."""

    @classmethod
    def setUpClass(cls) -> None:
        """Set up the provider, agent, and partner fixtures."""
        super().setUpClass()
        cls.provider = cls.env.ref('muk_ai.provider_openai')
        cls.provider.sudo().api_key = 'test-key'
        cls.env.company.default_ai_provider_id = cls.provider
        cls.agent = cls.env['muk_ai.agent'].create(
            {
                'name': 'Chain Strategy Agent',
            }
        )
        cls.partner_model = cls.env['ir.model']._get('res.partner')
        cls.partners = cls.env['res.partner'].create(
            [{'name': 'Chain Partner %d' % i} for i in range(2)]
        )

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
        """Create a per-record chained ``ai_agent`` action with defaults."""
        defaults = {
            'name': 'Chain Action',
            'state': 'ai_agent',
            'model_id': self.partner_model.id,
            'agent_id': self.agent.id,
            'agent_prompt': 'Hello.',
            'agent_dispatch_mode': 'per_record',
            'agent_record_source': 'domain',
            'agent_record_domain': "[('id', 'in', %s)]" % str(self.partners.ids),
            'agent_max_records_per_fire': 100,
            'agent_chain_strategy': 'per_record',
        }
        defaults.update(vals)
        return self.env['ir.actions.server'].create(defaults)

    def test_chain_per_record_links_previous_session(self):
        action = self._make_action()
        partner = self.partners[0]
        action.agent_record_domain = "[('id', '=', %d)]" % partner.id
        with self._mock_provider():
            first = fire_action(action, {})
        with self._mock_provider():
            second = fire_action(action, {})
        self.assertEqual(len(first), 1)
        self.assertEqual(len(second), 1)
        self.assertEqual(second.previous_session_id, first)

    def test_chain_none_does_not_link_previous(self):
        action = self._make_action(agent_chain_strategy='none')
        partner = self.partners[0]
        action.agent_record_domain = "[('id', '=', %d)]" % partner.id
        with self._mock_provider():
            first = fire_action(action, {})
        with self._mock_provider():
            second = fire_action(action, {})
        self.assertFalse(first.previous_session_id)
        self.assertFalse(second.previous_session_id)

    def test_chain_per_record_with_no_prior_session_leaves_previous_empty(
        self,
    ):
        action = self._make_action()
        partner = self.partners[0]
        action.agent_record_domain = "[('id', '=', %d)]" % partner.id
        with self._mock_provider():
            spawned = fire_action(action, {})
        self.assertEqual(len(spawned), 1)
        self.assertFalse(spawned.previous_session_id)
