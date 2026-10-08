from __future__ import annotations

import json
from collections.abc import Callable

import requests

from odoo.exceptions import UserError
from odoo.tools import mute_logger

from odoo.addons.muk_ai.tests.common import json_response, sse_response
from odoo.addons.muk_ai.tests.providers import (
    ATTACHMENTS,
    CASES,
    EFFORT,
    SYSTEM,
    TOOLS,
    USER,
    ProviderTestCase,
    deltas_of,
)

REJECTION = 'This model does not support the requested thinking effort.'


class TestProviders(ProviderTestCase):
    """Verify the request and stream contract every vendor adapter honours."""

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _either(
        self, events: list, payload: dict
    ) -> Callable[[dict], requests.Response]:
        """Answer a streamed POST with ``events`` and a plain one with ``payload``."""
        return lambda kwargs: (
            sse_response(events) if kwargs.get('stream') else json_response(payload)
        )

    def _assistant_content(self, result: dict) -> list:
        """Return the visible content of every assistant item the result carries."""
        return [
            item['content']
            for item in result['carry_inputs']
            if item.get('role') == 'assistant'
        ]

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_the_request_carries_model_system_tools_and_limits(self):
        schema = {'name': 'plan', 'schema': {'type': 'object'}}
        for name, case in CASES.items():
            provider = self.providers[name]
            for model, max_tokens in ((case.model, 2048), (None, 0)):
                with self.subTest(provider=name, model=model):
                    provider.max_tokens = max_tokens
                    _result, _deltas, sent = self._stream(
                        name,
                        case.text,
                        inputs=[SYSTEM, USER],
                        tools_schema=TOOLS,
                        text_schema=schema,
                        model=model,
                    )
                    sent_model = model or provider.default_chat_model_id.technical_name
                    url = sent[0]['url']
                    self.assertTrue(
                        url.endswith(case.endpoint.format(model=sent_model))
                    )
                    self.assertIs(sent[0]['stream'], True)
                    self.assertEqual(sent[0]['headers'][case.auth[0]], case.auth[1])
                    expected = {
                        'model': sent_model,
                        'system': 'be brief',
                        'tools': ['x'],
                        'max_tokens': max_tokens or case.unlimited,
                        'schema': schema['schema'],
                    }
                    wire = case.wire(url, sent[0]['json'])
                    self.assertEqual({key: wire[key] for key in expected}, expected)

    def test_streamed_text_and_tool_calls_reach_the_caller(self):
        for name, case in CASES.items():
            with self.subTest(provider=name, stream='text'):
                result, deltas, _sent = self._stream(name, case.text)
                self.assertEqual(deltas_of(deltas, 'text'), ['Hel', 'lo'])
                self.assertEqual(
                    (result['text'], result['tool_calls'], result['usage']),
                    ('Hello', [], case.usage),
                )
                self.assertEqual(
                    self._assistant_content(result),
                    [[{'type': 'output_text', 'text': 'Hello'}]],
                )
            with self.subTest(provider=name, stream='tool call'):
                result, deltas, _sent = self._stream(name, case.tool_call)
                starts = [data for kind, data in deltas if kind == 'tool_start']
                self.assertEqual([start['name'] for start in starts], ['do_x'])
                call_id = starts[0]['call_id']
                arguments = [data for kind, data in deltas if kind == 'tool_args']
                self.assertEqual({data['call_id'] for data in arguments}, {call_id})
                self.assertEqual(
                    json.loads(''.join(deltas_of(deltas, 'tool_args'))), {'a': 1}
                )
                self.assertEqual(
                    result['tool_calls'],
                    [
                        {
                            'call_id': call_id,
                            'name': 'do_x',
                            'arguments': {'a': 1},
                            '_parse_error': None,
                        }
                    ],
                )
                self.assertEqual(
                    [
                        (item['call_id'], json.loads(item['arguments']))
                        for item in result['carry_inputs']
                        if item.get('type') == 'function_call'
                    ],
                    [(call_id, {'a': 1})],
                )

    def test_reasoning_streams_apart_from_the_answer(self):
        for name, case in CASES.items():
            with self.subTest(provider=name):
                result, deltas, _sent = self._stream(name, case.reasoning)
                self.assertEqual(deltas_of(deltas, 'reasoning'), ['weighing it'])
                self.assertEqual(deltas_of(deltas, 'text'), ['answer'])
                self.assertEqual(result['text'], 'answer')
                self.assertEqual(
                    self._assistant_content(result),
                    [[{'type': 'output_text', 'text': 'answer'}]],
                )

    def test_a_max_token_stop_keeps_the_partial_answer_and_says_so(self):
        for name, case in CASES.items():
            with self.subTest(provider=name):
                result, deltas, _sent = self._stream(name, case.truncated)
                notice = deltas_of(deltas, 'text')[-1]
                self.assertIn('Max Tokens limit of 4096 tokens', notice)
                self.assertEqual(result['text'], f'partial{notice}')
                self.assertEqual(result['usage']['output_tokens'], 4096)

    def test_built_in_tools_follow_their_flags(self):
        for name, case in CASES.items():
            for web, code in (
                (False, False),
                (True, False),
                (False, True),
                (True, True),
            ):
                with self.subTest(provider=name, web=web, code=code):
                    _result, _deltas, sent = self._stream(
                        name,
                        case.text,
                        model=case.model,
                        enable_web_search=web,
                        enable_code_interpreter=code,
                    )
                    expected = [
                        tool
                        for tool, enabled in zip(case.builtin, (web, code), strict=True)
                        if enabled
                    ]
                    body = sent[0]['json']
                    self.assertEqual(
                        case.wire(sent[0]['url'], body)['builtin'], expected
                    )
                    self.assertEqual('tools' in body, bool(expected))

    def test_attachments_reach_each_vendor_in_its_native_form(self):
        for label, content, expected in ATTACHMENTS:
            for name, case in CASES.items():
                with self.subTest(attachment=label, provider=name):
                    _result, _deltas, sent = self._stream(
                        name, case.text, inputs=[{'role': 'user', 'content': content}]
                    )
                    self.assertEqual(
                        case.wire(sent[0]['url'], sent[0]['json'])['content'],
                        expected[name],
                    )

    def test_a_failed_request_raises_a_user_error(self):
        for name, case in CASES.items():
            for failure, answers, message in (
                (
                    'http',
                    [json_response({'error': {'message': 'server exploded'}}, 500)],
                    'server exploded',
                ),
                (
                    'transport',
                    [requests.ConnectionError('connection refused')],
                    'connection refused',
                ),
                ('stream', [[case.error('Overloaded')]], 'Overloaded'),
                ('key', [], 'API key is not configured'),
            ):
                with self.subTest(provider=name, failure=failure):
                    if not answers:
                        self.providers[name].sudo().api_key = False
                    with (
                        self._wire(*answers) as sent,
                        self.assertRaisesRegex(UserError, message),
                    ):
                        self.providers[name]._request_responses(
                            inputs=[USER], on_delta=lambda kind, data: None
                        )
                    self.assertEqual(len(sent), len(answers))

    def test_the_connection_test_needs_a_text_answer(self):
        for name, case in CASES.items():
            provider = self.providers[name]
            with self.subTest(provider=name):
                with self._wire(self._either(case.text, case.reply)) as sent:
                    action = provider.action_test_connection()
                self.assertEqual(len(sent), 1)
                self.assertEqual(action['params']['type'], 'success')
                with (
                    self._wire(self._either([], {})),
                    self.assertRaisesRegex(UserError, 'empty response'),
                ):
                    provider.action_test_connection()

    def test_reasoning_effort_is_clamped_to_the_model_and_mapped_per_vendor(self):
        for name, model, requested, expected in EFFORT:
            case = CASES[name]
            with self.subTest(provider=name, model=model, effort=requested):
                _result, _deltas, sent = self._stream(
                    name, case.text, model=model, reasoning_effort=requested
                )
                self.assertEqual(
                    case.wire(sent[0]['url'], sent[0]['json'])['effort'], expected
                )

    @mute_logger('odoo.addons.muk_ai.providers.base')
    def test_a_rejected_effort_is_dropped_only_before_any_output(self):
        for name, case in CASES.items():
            with self.subTest(provider=name, failure='rejected'):
                result, _deltas, sent = self._stream(
                    name,
                    json_response({'error': {'message': REJECTION}}, 400),
                    case.text,
                    model=case.model,
                    reasoning_effort='low',
                )
                self.assertEqual(
                    [
                        case.wire(record['url'], record['json'])['effort']
                        for record in sent
                    ],
                    ['low', None],
                )
                self.assertEqual(result['text'], 'Hello')
            for failure, answer in (
                ('unrelated', json_response({'error': {'message': 'exploded'}}, 500)),
                ('after output', [*case.text[:-1], case.error(REJECTION)]),
            ):
                with self.subTest(provider=name, failure=failure):
                    with (
                        self._wire(answer) as sent,
                        self.assertRaises(UserError),
                    ):
                        self.providers[name]._request_responses(
                            inputs=[USER],
                            model=case.model,
                            reasoning_effort='low',
                            on_delta=lambda kind, data: None,
                        )
                    self.assertEqual(len(sent), 1)
