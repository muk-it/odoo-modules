from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from odoo import models
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.web.controllers.utils import clean_action


@tagged('post_install', '-at_install')
class TestRunContract(TransactionCase):
    """Test the server-action return contract of the ``ai_agent`` runners."""

    @classmethod
    def setUpClass(cls) -> None:
        """Set up the provider, agent, and partner fixtures."""
        super().setUpClass()
        cls.provider = cls.env.ref('muk_ai.provider_openai')
        cls.provider.sudo().api_key = 'test-key'
        cls.env.company.default_ai_provider_id = cls.provider
        cls.agent = cls.env['muk_ai.agent'].create(
            {
                'name': 'Contract Agent',
            }
        )
        cls.partner_model = cls.env['ir.model']._get('res.partner')
        cls.partner = cls.env['res.partner'].create({'name': 'Contract Partner'})

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
            'name': 'Contract Action',
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

    def test_run_result_is_clean_action_safe(self):
        action = self._make_action()
        with self._mock_provider():
            result = action.with_context(
                active_model='res.partner',
                active_id=self.partner.id,
                active_ids=self.partner.ids,
            ).run()
        self.assertNotIsInstance(result, models.BaseModel)
        if result:
            clean_action(result, env=self.env)
        spawned = self.env['muk_ai.session'].search_count(
            [('action_server_id', '=', action.id)]
        )
        self.assertEqual(spawned, 1)

    def test_run_result_is_clean_action_safe_per_record(self):
        action = self._make_action(
            agent_dispatch_mode='per_record',
            agent_record_domain="[('id', 'in', %s)]" % str(self.partner.ids),
        )
        with self._mock_provider():
            result = action.run()
        self.assertNotIsInstance(result, models.BaseModel)
        if result:
            clean_action(result, env=self.env)
