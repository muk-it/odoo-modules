from __future__ import annotations

from odoo.exceptions import UserError
from odoo.tools import mute_logger

from odoo.addons.muk_ai.tests.common import json_response
from odoo.addons.muk_ai.tests.providers import (
    CASES,
    SYSTEM,
    TOOLS,
    USER,
    ProviderTestCase,
    anthropic_block,
    anthropic_text,
)

CALL = {'type': 'function_call', 'name': 't', 'arguments': '{"a": 1}', 'call_id': 'c1'}

OUTPUT = {'type': 'function_call_output', 'call_id': 'c1', 'output': {'ok': True}}

VOLATILE = {
    'role': 'user',
    'content': [{'type': 'input_text', 'text': '<ui_ctx/>'}],
    '_cache_volatile': True,
}

ANSWER = {'type': 'output_text', 'text': 'answer'}


class TestAnthropicProvider(ProviderTestCase):
    """Verify the Anthropic-only parts of the Messages wire: shape, cache, thinking."""

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _cache_marks(self, body: dict) -> list[tuple]:
        """Return where the request body places its ``cache_control`` breakpoints."""
        system = body.get('system')
        system = system if isinstance(system, list) else []
        blocks = [
            *((('system', index), block) for index, block in enumerate(system)),
            *(
                (('tools', index), tool)
                for index, tool in enumerate(body.get('tools') or [])
            ),
            *(
                (('messages', position, index), block)
                for position, message in enumerate(body['messages'])
                for index, block in enumerate(message['content'])
            ),
        ]
        return [place for place, block in blocks if 'cache_control' in block]

    def _thinking(self, index: int, text: str, signature: str = '') -> list[dict]:
        """Build the events of a streamed thinking block, signed when given one."""
        deltas = [{'type': 'thinking_delta', 'thinking': text}]
        if signature:
            deltas.append({'type': 'signature_delta', 'signature': signature})
        return anthropic_block(index, {'type': 'thinking', 'thinking': ''}, *deltas)

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_the_conversation_becomes_alternating_messages(self):
        _result, _deltas, sent = self._stream(
            'anthropic',
            CASES['anthropic'].text,
            model='open-model',
            inputs=[
                SYSTEM,
                {'role': 'system', 'content': 'stay polite'},
                USER,
                CALL,
                OUTPUT,
                {'role': 'user', 'content': 'next'},
            ],
            tools_schema=[*TOOLS, *TOOLS, {'name': 'y'}],
        )
        body = sent[0]['json']
        self.assertEqual(body['system'], 'be brief\n\nstay polite')
        self.assertEqual(
            body['messages'],
            [
                {'role': 'user', 'content': [{'type': 'text', 'text': 'hi'}]},
                {
                    'role': 'assistant',
                    'content': [
                        {'type': 'tool_use', 'id': 'c1', 'name': 't', 'input': {'a': 1}}
                    ],
                },
                {
                    'role': 'user',
                    'content': [
                        {
                            'type': 'tool_result',
                            'tool_use_id': 'c1',
                            'content': '{"ok": true}',
                        },
                        {'type': 'text', 'text': 'next'},
                    ],
                },
            ],
        )
        self.assertEqual(
            [(tool['name'], tool['input_schema']) for tool in body['tools']],
            [
                ('x', TOOLS[0]['parameters']),
                ('y', {'type': 'object', 'properties': {}}),
            ],
        )

    def test_cache_breakpoints_sit_before_the_volatile_tail(self):
        for model, inputs, tools, marks in (
            (
                'claude-sonnet-5',
                [SYSTEM, USER, VOLATILE],
                TOOLS,
                [('system', 0), ('tools', 0), ('messages', 0, 0)],
            ),
            (
                'claude-sonnet-5',
                [USER, CALL, OUTPUT, VOLATILE],
                None,
                [('messages', 2, 0)],
            ),
            ('open-model', [SYSTEM, USER, VOLATILE], TOOLS, []),
        ):
            with self.subTest(model=model, marks=marks):
                _result, _deltas, sent = self._stream(
                    'anthropic',
                    CASES['anthropic'].text,
                    model=model,
                    inputs=inputs,
                    tools_schema=tools,
                )
                self.assertEqual(self._cache_marks(sent[0]['json']), marks)

    def test_signed_thinking_is_carried_in_order_as_private_state(self):
        first = {'type': 'thinking', 'thinking': 'first', 'signature': 'sig-1'}
        redacted = {'type': 'redacted_thinking', 'data': 'opaque'}
        search = {'type': 'server_tool_use', 'id': 'srv_1', 'name': 'web_search'}
        found = {'type': 'web_search_tool_result', 'tool_use_id': 'srv_1'}
        for label, events, carried in (
            (
                'signed',
                [
                    *self._thinking(0, 'first', 'sig-1'),
                    *anthropic_block(
                        1,
                        {**search, 'input': {}},
                        {'type': 'input_json_delta', 'partial_json': '{"query": "x"}'},
                    ),
                    *anthropic_block(2, found),
                    *anthropic_block(3, redacted),
                    *self._thinking(4, 'second', 'sig-2'),
                    *anthropic_text(5, 'answer'),
                ],
                [
                    {
                        'role': 'assistant',
                        'content': [ANSWER],
                        'provider_state': {
                            'anthropic': {
                                'blocks': [
                                    first,
                                    {**search, 'input': {'query': 'x'}},
                                    found,
                                    redacted,
                                    {
                                        **first,
                                        'thinking': 'second',
                                        'signature': 'sig-2',
                                    },
                                    {'type': 'text', 'text': 'answer'},
                                ]
                            }
                        },
                    }
                ],
            ),
            (
                'unsigned',
                [*self._thinking(0, 'unsigned'), *anthropic_text(1, 'answer')],
                [{'role': 'assistant', 'content': [ANSWER]}],
            ),
            (
                'before a tool call',
                [
                    *self._thinking(0, 'first', 'sig-1'),
                    *anthropic_block(
                        1,
                        {'type': 'tool_use', 'id': 'toolu_1', 'name': 'do_x'},
                        {'type': 'input_json_delta', 'partial_json': '{"a": 1}'},
                    ),
                ],
                [
                    {
                        'role': 'assistant',
                        'content': [],
                        'provider_state': {'anthropic': {'blocks': [first]}},
                    },
                    {
                        'type': 'function_call',
                        'name': 'do_x',
                        'arguments': '{"a": 1}',
                        'call_id': 'toolu_1',
                    },
                ],
            ),
        ):
            with self.subTest(thinking=label):
                result, _deltas, _sent = self._stream('anthropic', events)
                self.assertEqual(result['carry_inputs'], carried)

    def test_legacy_thinking_budgets_leave_room_for_the_answer(self):
        for max_tokens, effort, budget, sent_max in (
            (4096, 'high', 4096, 5120),
            (8192, 'high', 4096, 8192),
            (0, 'medium', 1024, 4096),
        ):
            with self.subTest(max_tokens=max_tokens, effort=effort):
                self.providers['anthropic'].max_tokens = max_tokens
                result, _deltas, sent = self._stream(
                    'anthropic',
                    CASES['anthropic'].truncated,
                    model='claude-opus-4-5',
                    reasoning_effort=effort,
                )
                body = sent[0]['json']
                self.assertEqual(
                    (body['thinking'], body['max_tokens']),
                    ({'type': 'enabled', 'budget_tokens': budget}, sent_max),
                )
                self.assertIn(f'limit of {sent_max} tokens', result['text'])

    def test_a_response_schema_constrains_the_models_that_take_one(self):
        schema = {'name': 'plan', 'schema': {'type': 'object'}}
        for model, output in (
            (
                'claude-opus-5',
                {
                    'effort': 'low',
                    'format': {'type': 'json_schema', 'schema': {'type': 'object'}},
                },
            ),
            ('claude-sonnet-4-6', {'effort': 'low'}),
        ):
            with self.subTest(model=model):
                _result, _deltas, sent = self._stream(
                    'anthropic',
                    CASES['anthropic'].text,
                    model=model,
                    text_schema=schema,
                    reasoning_effort='low',
                )
                self.assertEqual(sent[0]['json']['output_config'], output)

    @mute_logger('odoo.addons.muk_ai.providers.base')
    def test_a_rejection_the_retry_cannot_resolve_raises(self):
        rejected = {'error': {'message': 'This model does not support thinking.'}}
        with (
            self._wire(
                json_response(rejected, 400), json_response(rejected, 400)
            ) as sent,
            self.assertRaisesRegex(UserError, 'does not support thinking'),
        ):
            self.providers['anthropic']._request_responses(
                inputs=[USER],
                model='claude-opus-4-8',
                reasoning_effort='low',
                on_delta=lambda kind, data: None,
            )
        self.assertEqual(
            [
                (record['json'].get('thinking'), record['json'].get('output_config'))
                for record in sent
            ],
            [({'type': 'adaptive'}, {'effort': 'low'}), ({'type': 'adaptive'}, None)],
        )
