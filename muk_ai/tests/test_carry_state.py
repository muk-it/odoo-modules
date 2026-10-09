from __future__ import annotations

import json

from odoo.addons.muk_ai.tests.providers import CASES, USER, ProviderTestCase

CALL = {
    'type': 'function_call',
    'name': 'search_read',
    'arguments': '{"model": "res.partner"}',
    'call_id': 'call_google_1',
}

SIGNED_CALL = {
    **CALL,
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

OUTPUT = {
    'type': 'function_call_output',
    'call_id': 'call_google_1',
    'output': '{"count": 3}',
}

STEPS = [
    {'type': 'thinking', 'thinking': 'step one', 'signature': 'sig-1'},
    {'type': 'thinking', 'thinking': 'step two', 'signature': 'sig-2'},
]

THINKING_TURN = {
    'role': 'assistant',
    'content': [{'type': 'output_text', 'text': 'answer'}],
    'provider_state': {
        'anthropic': {
            'blocks': [
                STEPS[0],
                {'type': 'server_tool_use', 'id': 'srv_1', 'name': 'web_search'},
                {'type': 'web_search_tool_result', 'tool_use_id': 'srv_1'},
                STEPS[1],
                {'type': 'text', 'text': 'answer'},
            ]
        }
    },
}


class TestCarryState(ProviderTestCase):
    """Verify provider-private carry state reaches its owner and no other vendor."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        """Create one agent per vendor, on that vendor's default chat model."""
        super().setUpClass()
        cls.agents = {
            name: cls.env['muk_ai.agent'].create(
                {'name': name, 'model_id': provider.default_chat_model_id.id}
            )
            for name, provider in cls.providers.items()
        }

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _next_turn(self, name: str, conversation: list) -> dict:
        """Continue a chat with the vendor's agent and return the body it was sent.

        The declared tools are left out, so only the conversation is compared.
        """
        session = self._session(agent_id=self.agents[name].id)
        session.conversation = conversation
        with self._wire(CASES[name].text) as sent:
            session.send_message('next')
        self.assertEqual(session.state, 'done')
        return {key: value for key, value in sent[0]['json'].items() if key != 'tools'}

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_no_vendor_sees_internal_keys_or_another_vendors_state(self):
        for owner, item, secrets in (
            (None, {**USER, '_cache_volatile': True}, ['_cache_volatile']),
            (None, {**USER, '_answer_entry': True}, ['_answer_entry']),
            (
                None,
                {
                    'role': 'assistant',
                    'content': [
                        {
                            'type': 'muk_ai_thinking',
                            'thinking': 'stale',
                            'signature': '',
                        },
                        {'type': 'output_text', 'text': 'answer'},
                    ],
                },
                ['muk_ai_thinking', 'stale'],
            ),
            ('google', SIGNED_CALL, ['provider_state', 'thoughtSignature', 'sig-a']),
            ('anthropic', THINKING_TURN, ['provider_state', 'sig-1', 'step one']),
            (
                'openai_compat',
                {
                    **THINKING_TURN,
                    'provider_state': {
                        'openai_compat': THINKING_TURN['provider_state']['anthropic']
                    },
                },
                ['provider_state', 'sig-1', 'step one'],
            ),
        ):
            for name, case in CASES.items():
                if name == owner:
                    continue
                with self.subTest(owner=owner, secret=secrets[0], provider=name):
                    _result, _deltas, sent = self._stream(
                        name, case.text, inputs=[USER, item]
                    )
                    body = json.dumps(sent[0]['json'])
                    self.assertEqual(
                        [secret for secret in secrets if secret in body], []
                    )

    def test_a_handoff_hands_the_next_vendor_a_clean_request(self):
        signed = [USER, {**SIGNED_CALL, '_internal': 'gone'}, OUTPUT]
        foreign = [
            USER,
            {**CALL, 'call_id': 'call_openai_1'},
            {**OUTPUT, 'call_id': 'call_openai_1'},
        ]
        for name, conversation, present, absent in (
            (
                'openai',
                signed,
                ['call_google_1'],
                ['provider_state', 'sig-a', '_internal'],
            ),
            (
                'anthropic',
                signed,
                ['call_google_1'],
                ['provider_state', 'sig-a', '_internal'],
            ),
            ('google', signed, ['sig-a'], ['provider_state', '_internal']),
            (
                'google',
                foreign,
                ['[tool call] search_read', '[tool result] search_read'],
                ['functionCall', 'functionResponse'],
            ),
        ):
            with self.subTest(provider=name, call=conversation[1]['call_id']):
                body = json.dumps(self._next_turn(name, conversation))
                self.assertEqual([text for text in present if text not in body], [])
                self.assertEqual([text for text in absent if text in body], [])

    def test_anthropic_replays_its_turn_blocks_as_they_came(self):
        searched = [
            ('thinking', 'sig-1'),
            ('server_tool_use', None),
            ('web_search_tool_result', None),
            ('thinking', 'sig-2'),
            ('text', None),
        ]
        for label, conversation, blocks in (
            ('answer', [USER, THINKING_TURN], searched),
            (
                'tool call',
                [
                    USER,
                    THINKING_TURN,
                    {**CALL, 'call_id': 'toolu_1'},
                    {**OUTPUT, 'call_id': 'toolu_1'},
                ],
                [*searched, ('tool_use', None)],
            ),
            (
                'older carry',
                [
                    USER,
                    {
                        **THINKING_TURN,
                        'provider_state': {'anthropic': {'thinking': STEPS}},
                    },
                ],
                [('text', None)],
            ),
        ):
            with self.subTest(label):
                body = self._next_turn('anthropic', conversation)
                assistant = next(
                    message['content']
                    for message in body['messages']
                    if message['role'] == 'assistant'
                )
                self.assertEqual(
                    [(block['type'], block.get('signature')) for block in assistant],
                    blocks,
                )
