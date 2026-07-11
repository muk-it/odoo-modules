from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from odoo import models
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.muk_ai_automation.tools.dispatch import (
    PreviousProxy,
    _create_session,
    _resolve_records,
)


@tagged('post_install', '-at_install', 'muk_ai_automation')
class TestDispatchHelper(TransactionCase):
    """Test the dispatch helper functions in isolation."""

    @classmethod
    def setUpClass(cls) -> None:
        """Set up the provider, agent, and partner fixtures."""
        super().setUpClass()
        cls.provider = cls.env.ref('muk_ai.provider_openai')
        cls.provider.sudo().api_key = 'test-key'
        cls.env.company.default_ai_provider_id = cls.provider
        cls.agent = cls.env['muk_ai.agent'].create(
            {
                'name': 'Dispatch Helper Agent',
            }
        )
        cls.partner_model = cls.env['ir.model']._get('res.partner')
        cls.partners = cls.env['res.partner'].create(
            [{'name': 'Helper Partner %d' % i} for i in range(4)]
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
            'name': 'Helper Action',
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

    def test_resolve_records_via_domain(self):
        target = self.partners[:2]
        action = self._make_action(
            agent_record_domain="[('id', 'in', %s)]" % str(target.ids),
        )
        records = _resolve_records(action, {})
        self.assertEqual(sorted(records.ids), sorted(target.ids))

    def test_resolve_records_via_code(self):
        action = self._make_action(
            agent_record_source='code',
            agent_record_code='records = env["res.partner"].search([], limit=2)',
        )
        records = _resolve_records(action, {})
        self.assertEqual(records._name, 'res.partner')
        self.assertEqual(len(records), 2)

    def test_resolve_records_invalid_code_returns_empty(self):
        action = self._make_action(
            agent_record_source='code',
            agent_record_code='this is not valid python <<<',
        )
        records = _resolve_records(action, {})
        self.assertEqual(len(records), 0)
        self.assertEqual(records._name, 'res.partner')

    def test_previous_proxy_with_no_session(self):
        proxy = PreviousProxy(None)
        self.assertEqual(proxy.last_text, '')
        self.assertEqual(proxy.tool_log, [])

    def test_previous_proxy_tool_log_with_logged_session(self):
        session = self.env['muk_ai.session'].create({'name': 'Logged Session'})
        self.env['muk_mcp.log'].sudo().create(
            {
                'tool_name': 'search',
                'request_data': '{"model": "res.partner"}',
                'response_data': '{"ids": [1]}',
                'session_id': session.id,
                'source': 'chat',
            }
        )
        log = PreviousProxy(session).tool_log
        self.assertEqual(len(log), 1)
        self.assertEqual(log[0]['name'], 'search')
        self.assertEqual(log[0]['arguments'], {'model': 'res.partner'})
        self.assertEqual(log[0]['output'], {'ids': [1]})

    def test_create_session_writes_action_server_id(self):
        action = self._make_action()
        with self._mock_provider():
            session = _create_session(action, 'Hello.', None)
        self.assertEqual(session.action_server_id, action)
        self.assertEqual(session.agent_id, self.agent)
