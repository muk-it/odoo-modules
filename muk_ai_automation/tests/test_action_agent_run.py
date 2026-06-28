from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from odoo import models
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install', 'muk_ai_automation')
class TestActionAgentRun(TransactionCase):
    """Test session spawning when running an ``ai_agent`` server action."""

    @classmethod
    def setUpClass(cls) -> None:
        """Set up the provider, agent, and partner fixtures."""
        super().setUpClass()
        cls.provider = cls.env.ref('muk_ai.provider_openai')
        cls.provider.sudo().api_key = 'test-key'
        cls.env.company.default_ai_provider_id = cls.provider
        cls.agent = cls.env['muk_ai.agent'].create(
            {
                'name': 'Action Run Agent',
            }
        )
        cls.partner_model = cls.env['ir.model']._get('res.partner')
        cls.partners = cls.env['res.partner'].create(
            [{'name': 'Action Partner %d' % i} for i in range(3)]
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
            'name': 'Run Agent Action',
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

    def test_run_action_agent_single_creates_one_session(self):
        action = self._make_action()
        Session = self.env['muk_ai.session']
        before = Session.search_count([('action_server_id', '=', action.id)])
        with self._mock_provider():
            action.run()
        after = Session.search_count([('action_server_id', '=', action.id)])
        self.assertEqual(after - before, 1)

    def test_run_action_agent_per_record_creates_n_sessions(self):
        action = self._make_action(
            agent_dispatch_mode='per_record',
            agent_record_domain=self._domain_for(self.partners),
            agent_max_records_per_fire=100,
        )
        Session = self.env['muk_ai.session']
        before = Session.search_count([('action_server_id', '=', action.id)])
        with self._mock_provider():
            action.run()
        after = Session.search_count([('action_server_id', '=', action.id)])
        self.assertEqual(after - before, 3)

    def test_run_action_agent_links_session_to_action(self):
        action = self._make_action()
        with self._mock_provider():
            action.run()
        session = self.env['muk_ai.session'].search(
            [('action_server_id', '=', action.id)],
            limit=1,
        )
        self.assertTrue(session)
        self.assertEqual(session.action_server_id, action)

    def test_run_without_agent_raises(self):
        action = self._make_action()
        action.agent_id = False
        with self._mock_provider():
            with self.assertRaises(UserError):
                action.run()
