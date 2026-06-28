from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from odoo import models
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install', 'muk_ai_automation')
class TestBaseAutomationPath(TransactionCase):
    """Test agent dispatch triggered through a base automation rule."""

    @classmethod
    def setUpClass(cls) -> None:
        """Set up the provider, agent, and partner model fixtures."""
        super().setUpClass()
        cls.provider = cls.env.ref('muk_ai.provider_openai')
        cls.provider.sudo().api_key = 'test-key'
        cls.env.company.default_ai_provider_id = cls.provider
        cls.agent = cls.env['muk_ai.agent'].create(
            {
                'name': 'Automation Path Agent',
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
            'name': 'Automation Action',
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

    def test_on_create_partner_fires_agent_action(self):
        action = self._make_action()
        automation = self.env['base.automation'].create(
            {
                'name': 'Run AI on partner create',
                'model_id': self.partner_model.id,
                'trigger': 'on_create',
                'action_server_ids': [(6, 0, [action.id])],
            }
        )
        Session = self.env['muk_ai.session']
        before = Session.search_count([('action_server_id', '=', action.id)])
        with self._mock_provider():
            self.env['res.partner'].create({'name': 'Trigger Partner'})
        after = Session.search_count([('action_server_id', '=', action.id)])
        self.assertGreater(after, before)
        self.assertTrue(automation.exists())

    def test_base_automation_id_related_filled(self):
        action = self._make_action()
        automation = self.env['base.automation'].create(
            {
                'name': 'Run AI on partner create',
                'model_id': self.partner_model.id,
                'trigger': 'on_create',
                'action_server_ids': [(6, 0, [action.id])],
            }
        )
        with self._mock_provider():
            self.env['res.partner'].create({'name': 'Related Partner'})
        session = self.env['muk_ai.session'].search(
            [('action_server_id', '=', action.id)],
            limit=1,
        )
        self.assertTrue(session)
        self.assertEqual(session.base_automation_id, automation)
