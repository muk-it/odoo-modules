from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from odoo import models
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.muk_ai_automation.tools.dispatch import fire_action


@tagged('post_install', '-at_install', 'muk_ai_automation')
class TestDispatchModes(TransactionCase):
    """Test single and per-record dispatch modes and their caps."""

    @classmethod
    def setUpClass(cls) -> None:
        """Set up the provider, agent, and partner fixtures."""
        super().setUpClass()
        cls.provider = cls.env.ref('muk_ai.provider_openai')
        cls.provider.sudo().api_key = 'test-key'
        cls.env.company.default_ai_provider_id = cls.provider
        cls.agent = cls.env['muk_ai.agent'].create(
            {
                'name': 'Dispatch Modes Agent',
            }
        )
        cls.partner_model = cls.env['ir.model']._get('res.partner')
        cls.partners = cls.env['res.partner'].create(
            [{'name': 'Mode Partner %d' % i} for i in range(5)]
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
        """Create an ``ai_agent`` server action with overridable defaults."""
        defaults = {
            'name': 'Mode Action',
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

    def _domain_for(self, partners) -> str:
        """Return a domain string matching the given partners by id."""
        return "[('id', 'in', %s)]" % str(partners.ids)

    def test_single_mode_one_session(self):
        action = self._make_action()
        with self._mock_provider():
            spawned = fire_action(action, {})
        self.assertEqual(len(spawned), 1)

    def test_per_record_mode_one_per_record(self):
        partners = self.partners[:3]
        action = self._make_action(
            agent_dispatch_mode='per_record',
            agent_record_domain=self._domain_for(partners),
            agent_max_records_per_fire=100,
        )
        with self._mock_provider():
            spawned = fire_action(action, {})
        self.assertEqual(len(spawned), 3)
        self.assertEqual(
            sorted(spawned.mapped('res_id')),
            sorted(partners.ids),
        )

    def test_per_record_mode_caps_at_max_records_per_fire(self):
        action = self._make_action(
            agent_dispatch_mode='per_record',
            agent_record_domain=self._domain_for(self.partners),
            agent_max_records_per_fire=2,
        )
        with self._mock_provider():
            spawned = fire_action(action, {})
        self.assertEqual(len(spawned), 2)

    def test_per_record_mode_empty_domain_no_sessions(self):
        action = self._make_action(
            agent_dispatch_mode='per_record',
            agent_record_domain="[('id', '=', -1)]",
            agent_max_records_per_fire=100,
        )
        with self._mock_provider():
            spawned = fire_action(action, {})
        self.assertFalse(spawned)
