from __future__ import annotations

import importlib.util
import json
import pathlib
from types import ModuleType
from unittest.mock import patch

import requests

from odoo import models
from odoo.tests import tagged

from odoo.addons.muk_ai.tests.common import AITestCommon


@tagged('post_install', '-at_install', 'muk_ai')
class TestCarryState(AITestCommon):
    """Verify provider-private carry state is kept, replayed, and never shared."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.gemini = cls._chat_model(cls.provider_google, 'gemini-3.8-flash')
        cls.gpt = cls._chat_model(cls.provider, 'gpt-5.6-terra')
        cls.claude = cls._chat_model(cls.provider_anthropic, 'claude-sonnet-5')
        agents = cls.env['muk_ai.agent']
        cls.agent_google = agents.create(
            {'name': 'Gemini Agent', 'model_id': cls.gemini.id}
        )
        cls.agent_openai = agents.create({'name': 'GPT Agent', 'model_id': cls.gpt.id})
        cls.agent_anthropic = agents.create(
            {'name': 'Claude Agent', 'model_id': cls.claude.id}
        )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @classmethod
    def _chat_model(
        cls, provider: models.BaseModel, technical_name: str
    ) -> models.BaseModel:
        """Return the catalogued chat model of the provider, creating it if absent."""
        model = (
            cls.env['muk_ai.model']
            .with_context(active_test=False)
            .search(
                [
                    ('provider_id', '=', provider.id),
                    ('technical_name', '=', technical_name),
                ],
                limit=1,
            )
        )
        if not model:
            model = cls.env['muk_ai.model'].create(
                {
                    'name': technical_name,
                    'provider_id': provider.id,
                    'technical_name': technical_name,
                    'context_window': 400000,
                    'input_rate': 1.0,
                    'output_rate': 1.0,
                }
            )
        model.active = True
        return model

    def _google_carry(self, call_id: str = 'call_google_1') -> dict:
        """Build the function-call item a signed Gemini round stores."""
        return {
            'type': 'function_call',
            'name': 'search_read',
            'arguments': '{"model": "res.partner"}',
            'call_id': call_id,
            'provider_state': {
                'google': {
                    'parts': [
                        {
                            'functionCall': {
                                'name': 'search_read',
                                'args': {'model': 'res.partner'},
                            },
                            'thoughtSignature': 'sig-a',
                        }
                    ]
                }
            },
        }

    def _anthropic_carry(self, text: str = 'answer') -> dict:
        """Build the assistant item a signed Claude turn stores.

        :param text: the visible answer of the turn, empty when it only
            thought before calling a tool.
        """
        return {
            'role': 'assistant',
            'content': [{'type': 'output_text', 'text': text}] if text else [],
            'provider_state': {
                'anthropic': {
                    'thinking': [
                        {
                            'type': 'thinking',
                            'thinking': 'step one',
                            'signature': 'sig-1',
                        },
                        {
                            'type': 'thinking',
                            'thinking': 'step two',
                            'signature': 'sig-2',
                        },
                    ]
                }
            },
        }

    def _legacy_thinking_turn(self) -> dict:
        """Build the assistant item a conversation stored before the split.

        The canonical block type is gone; a conversation written while it
        existed still holds one, and no vendor may be handed it.
        """
        return {
            'role': 'assistant',
            'content': [
                {
                    'type': 'muk_ai_thinking',
                    'thinking': 'stale reasoning',
                    'signature': '',
                },
                {'type': 'output_text', 'text': 'answer'},
            ],
        }

    def _tool_output(self, call_id: str = 'call_google_1') -> dict:
        """Build the tool result item answering a carried function call."""
        return {
            'type': 'function_call_output',
            'call_id': call_id,
            'output': '{"count": 3}',
        }

    def _sent_body(self, provider: models.BaseModel, inputs: list) -> dict:
        """Run one non-streaming request and return the body that was sent."""
        captured = {}

        def fake_post(url, **kwargs):
            captured['body'] = kwargs.get('json')
            return self._mock_http_response({})

        with patch.object(requests.Session, 'post', side_effect=fake_post):
            provider._request_responses(inputs=inputs)
        return captured['body']

    def _load_migration(self, version: str) -> ModuleType:
        """Import the post-migrate script of the given version by path.

        :return: the loaded module exposing ``migrate(cr, version)``
        """
        path = (
            pathlib.Path(__file__).resolve().parents[1]
            / 'migrations'
            / version
            / 'post-migrate.py'
        )
        spec = importlib.util.spec_from_file_location(
            f'muk_ai_m{version.replace(".", "")}', path
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def _session_inputs(self, agent: models.BaseModel, conversation: list) -> list:
        """Return the request inputs a session on the agent builds for a history."""
        session = self.env['muk_ai.session'].create(
            {'name': 'carry', 'agent_id': agent.id}
        )
        session.conversation = conversation
        return session._build_request_inputs()

    # ----------------------------------------------------------
    # Tests: isolation
    # ----------------------------------------------------------

    def test_openai_never_sends_another_vendors_state(self):
        body = self._sent_body(
            self.provider,
            [self._google_carry(), self._tool_output()],
        )
        self.assertNotIn('provider_state', json.dumps(body))
        self.assertNotIn('thoughtSignature', json.dumps(body))
        self.assertEqual(body['input'][0]['call_id'], 'call_google_1')

    def test_openai_never_sends_the_internal_cache_marker(self):
        body = self._sent_body(
            self.provider,
            [
                {
                    'role': 'user',
                    'content': [{'type': 'input_text', 'text': 'hi'}],
                    '_cache_volatile': True,
                }
            ],
        )
        self.assertNotIn('_cache_volatile', json.dumps(body))

    def test_google_never_sends_another_vendors_state(self):
        body = self._sent_body(
            self.provider_google,
            [
                {
                    'type': 'function_call',
                    'name': 'search_read',
                    'arguments': '{}',
                    'call_id': 'call_openai_1',
                    'provider_state': {'openai': {'encrypted': 'secret'}},
                }
            ],
        )
        self.assertNotIn('secret', json.dumps(body))
        parts = body['contents'][0]['parts']
        self.assertEqual(list(parts[0]), ['text'])

    def test_a_provider_reads_only_the_slot_it_owns(self):
        client = self.provider_google._get_client()
        item = {'provider_state': {'openai': {'a': 1}, 'google': {'b': 2}}}
        self.assertEqual(client._carried_state(item), {'b': 2})
        self.assertEqual(self.provider._get_client()._carried_state(item), {'a': 1})
        self.assertEqual(client._carried_state({}), {})

    # ----------------------------------------------------------
    # Tests: round trip
    # ----------------------------------------------------------

    def test_a_stored_conversation_keeps_the_state_but_no_internals(self):
        conversation = [
            {**self._google_carry(), '_internal': 'gone'},
            self._tool_output(),
        ]
        inputs = self._session_inputs(self.agent_google, conversation)
        carried = next(item for item in inputs if item.get('type') == 'function_call')
        self.assertEqual(
            carried['provider_state']['google']['parts'][0]['thoughtSignature'],
            'sig-a',
        )
        body = self._sent_body(self.provider_google, inputs)
        self.assertNotIn('_internal', json.dumps(body))
        self.assertIn('sig-a', json.dumps(body))
        self.assertNotIn(
            '_internal', json.dumps(self._sent_body(self.provider, inputs))
        )

    def test_a_handoff_hands_the_next_vendor_a_clean_request(self):
        conversation = [self._google_carry(), self._tool_output()]
        body = self._sent_body(
            self.provider,
            self._session_inputs(self.agent_openai, conversation),
        )
        self.assertNotIn('provider_state', json.dumps(body))
        self.assertNotIn('_cache_volatile', json.dumps(body))
        self.assertTrue(
            any(
                item.get('type') == 'function_call'
                and item.get('call_id') == 'call_google_1'
                for item in body['input']
            )
        )

    def test_a_handoff_to_google_replays_a_foreign_call_as_text(self):
        conversation = [
            {
                'type': 'function_call',
                'name': 'search_count',
                'arguments': '{"model": "res.partner"}',
                'call_id': 'call_openai_1',
            },
            self._tool_output('call_openai_1'),
        ]
        body = self._sent_body(
            self.provider_google,
            self._session_inputs(self.agent_google, conversation),
        )
        self.assertNotIn('functionCall', json.dumps(body))
        self.assertIn('[tool call] search_count', json.dumps(body))
        self.assertIn('[tool result] search_count', json.dumps(body))

    def test_a_handoff_back_replays_the_signature(self):
        conversation = [self._google_carry(), self._tool_output()]
        body = self._sent_body(
            self.provider_google,
            self._session_inputs(self.agent_google, conversation),
        )
        model_parts = next(
            content for content in body['contents'] if content['role'] == 'model'
        )['parts']
        self.assertEqual(model_parts[0]['thoughtSignature'], 'sig-a')

    # ----------------------------------------------------------
    # Tests: thinking
    # ----------------------------------------------------------

    def test_anthropic_replays_its_thinking_ahead_of_the_turn_text(self):
        body = self._sent_body(
            self.provider_anthropic,
            self._session_inputs(self.agent_anthropic, [self._anthropic_carry()]),
        )
        content = next(
            message for message in body['messages'] if message['role'] == 'assistant'
        )['content']
        self.assertEqual(
            [(block['type'], block.get('signature')) for block in content],
            [('thinking', 'sig-1'), ('thinking', 'sig-2'), ('text', None)],
        )

    def test_anthropic_replays_its_thinking_ahead_of_its_tool_use(self):
        conversation = [
            self._anthropic_carry(text=''),
            {
                'type': 'function_call',
                'name': 'search_read',
                'arguments': '{}',
                'call_id': 'call_anthropic_1',
            },
            self._tool_output('call_anthropic_1'),
        ]
        body = self._sent_body(
            self.provider_anthropic,
            self._session_inputs(self.agent_anthropic, conversation),
        )
        content = next(
            message for message in body['messages'] if message['role'] == 'assistant'
        )['content']
        self.assertEqual(
            [block['type'] for block in content],
            ['thinking', 'thinking', 'tool_use'],
        )

    def test_a_handoff_to_anthropic_sends_no_foreign_thinking(self):
        conversation = [
            {
                'role': 'assistant',
                'content': [{'type': 'output_text', 'text': 'answer'}],
                'provider_state': {'openai_compat': {'thinking': [{'type': 'x'}]}},
            }
        ]
        body = self._sent_body(
            self.provider_anthropic,
            self._session_inputs(self.agent_anthropic, conversation),
        )
        self.assertNotIn('thinking', json.dumps(body['messages']))

    def test_a_handoff_from_anthropic_never_leaks_its_signatures(self):
        inputs = self._session_inputs(self.agent_openai, [self._anthropic_carry()])
        for provider in (self.provider, self.provider_google):
            body = json.dumps(self._sent_body(provider, inputs))
            self.assertNotIn('sig-1', body)
            self.assertNotIn('step one', body)

    def test_a_thinking_block_stored_before_the_split_reaches_no_vendor(self):
        conversation = [self._legacy_thinking_turn()]
        for agent, provider in (
            (self.agent_anthropic, self.provider_anthropic),
            (self.agent_openai, self.provider),
            (self.agent_google, self.provider_google),
        ):
            body = json.dumps(
                self._sent_body(provider, self._session_inputs(agent, conversation))
            )
            self.assertNotIn('muk_ai_thinking', body)
            self.assertNotIn('stale reasoning', body)

    # ----------------------------------------------------------
    # Tests: migration
    # ----------------------------------------------------------

    def test_the_migration_files_a_signed_thought_under_anthropic(self):
        legacy = self._legacy_thinking_turn()
        legacy['content'][0]['signature'] = 'sig-1'
        session = self.env['muk_ai.session'].create(
            {'name': 'legacy', 'agent_id': self.agent_anthropic.id}
        )
        session.conversation = [legacy]
        self.env.flush_all()
        self._load_migration('17.0.1.19.10').migrate(self.env.cr, '17.0.1.19.9')
        session.invalidate_recordset(['conversation'])
        item = session.conversation[0]
        self.assertEqual(item['content'], [{'type': 'output_text', 'text': 'answer'}])
        self.assertEqual(
            item['provider_state']['anthropic']['thinking'],
            [
                {
                    'type': 'thinking',
                    'thinking': 'stale reasoning',
                    'signature': 'sig-1',
                }
            ],
        )
        body = self._sent_body(self.provider_anthropic, session._build_request_inputs())
        self.assertIn('sig-1', json.dumps(body))

    def test_the_migration_drops_an_unsigned_thought(self):
        session = self.env['muk_ai.session'].create(
            {'name': 'legacy', 'agent_id': self.agent_openai.id}
        )
        session.conversation = [self._legacy_thinking_turn()]
        self.env.flush_all()
        self._load_migration('17.0.1.19.10').migrate(self.env.cr, '17.0.1.19.9')
        session.invalidate_recordset(['conversation'])
        item = session.conversation[0]
        self.assertEqual(item['content'], [{'type': 'output_text', 'text': 'answer'}])
        self.assertNotIn('provider_state', item)
