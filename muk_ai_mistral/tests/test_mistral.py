from unittest.mock import patch

import requests

from odoo.exceptions import UserError

from odoo.addons.muk_ai.tests.common import json_response
from odoo.addons.muk_ai.tests.providers import (
    FILE_TEXT,
    TEXT_FILE,
    TOOLS,
    USER,
    ProviderCase,
    _attached,
    deltas_of,
)
from odoo.addons.muk_ai.tests.test_providers import TestProviders

PNG = b'\x89PNG\r\n\x1a\n'


def delta(content) -> dict:
    """Build a ``message.output.delta`` event of the Conversations stream."""
    return {'type': 'message.output.delta', 'output_index': 0, 'content': content}


def done(prompt: int = 1, completion: int = 1) -> dict:
    """Build the event closing a Conversations stream with its usage."""
    return {
        'type': 'conversation.response.done',
        'usage': {'prompt_tokens': prompt, 'completion_tokens': completion},
    }


def call(name: str, *arguments: str) -> list[dict]:
    """Build the deltas of one streamed function call."""
    return [
        {
            'type': 'function.call.delta',
            'output_index': 1,
            'tool_call_id': 'c1',
            'name': name,
            'arguments': chunk,
        }
        for chunk in arguments
    ]


def _mistral_wire(url: str, body: dict) -> dict:
    """Normalise a Mistral Conversations request body."""
    tools = body.get('tools') or []
    args = body.get('completion_args') or {}
    return {
        'model': body['model'],
        'system': body.get('instructions') or '',
        'tools': [tool['function']['name'] for tool in tools if 'function' in tool],
        'builtin': [tool['type'] for tool in tools if 'function' not in tool],
        'max_tokens': args.get('max_tokens'),
        'effort': None,
        'schema': (args.get('response_format') or {})
        .get('json_schema', {})
        .get('schema'),
        'content': body['inputs'][-1]['content'],
    }


MISTRAL = ProviderCase(
    xmlid='muk_ai_mistral.provider_mistral',
    model='mistral-small-latest',
    endpoint='/conversations',
    auth=('Authorization', 'Bearer test-key'),
    builtin=('web_search', 'code_interpreter'),
    unlimited=None,
    text=[
        {'type': 'conversation.response.started'},
        delta('Hel'),
        delta('lo'),
        done(11, 4),
    ],
    usage={
        'input_tokens': 11,
        'output_tokens': 4,
        'cache_read_tokens': 0,
        'cache_write_tokens': 0,
    },
    tool_call=[*call('do_x', '', '{"a":', '1}'), done()],
    reasoning=[
        delta(
            {'type': 'thinking', 'thinking': [{'type': 'text', 'text': 'weighing it'}]}
        ),
        delta('answer'),
        done(),
    ],
    truncated=[delta('partial'), done(7, 4096)],
    reply={},
    error=lambda message: {
        'type': 'conversation.response.error',
        'message': message,
        'code': 3000,
    },
    wire=_mistral_wire,
)

ATTACHMENTS = [
    (
        'image',
        _attached(strategy='image', mimetype='image/png', data_b64='AAA='),
        {'mistral': [{'type': 'image_url', 'image_url': 'data:image/png;base64,AAA='}]},
    ),
    (
        'pdf',
        _attached(strategy='file', mimetype='application/pdf', data_b64='PDF='),
        {
            'mistral': [
                {
                    'type': 'document_url',
                    'document_url': 'data:application/pdf;base64,PDF=',
                }
            ]
        },
    ),
    (
        'text',
        _attached(**TEXT_FILE),
        {'mistral': [{'type': 'text', 'text': FILE_TEXT}]},
    ),
    ('plain string', 'hi', {'mistral': [{'type': 'text', 'text': 'hi'}]}),
]


class TestMistral(TestProviders):
    """Run the provider contract and the connectors on Mistral's wire."""

    allow_inherited_tests_method = True
    cases = {'mistral': MISTRAL}
    attachments = ATTACHMENTS
    efforts = ()

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        """Give the Mistral account a key and lift its rate limit."""
        super().setUpClass()
        cls.providers['mistral'].write({'api_key': 'test-key', 'rate_limit': 0})

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_the_account_is_seeded_with_its_default_models(self):
        provider = self.providers['mistral']
        self.assertEqual(
            (
                provider.default_chat_model_id.technical_name,
                provider.default_image_model_id.modality,
                provider._get_client().api_url,
            ),
            ('mistral-medium-latest', 'image', 'https://api.mistral.ai/v1'),
        )

    def test_reserved_tool_names_travel_under_a_prefix_and_come_back(self):
        history = [
            USER,
            {'type': 'function_call', 'name': 'web_search', 'call_id': 'c0'},
            {'type': 'function_call_output', 'call_id': 'c0', 'output': {'ok': 1}},
            {'role': 'assistant', 'content': [{'type': 'output_text', 'text': 'ok'}]},
        ]
        result, deltas, sent = self._stream(
            'mistral',
            [*call('muk_ai_web_search', '{}'), done()],
            inputs=history,
            tools_schema=[{**TOOLS[0], 'name': 'web_search'}],
        )
        body = sent[0]['json']
        self.assertEqual(body['tools'][0]['function']['name'], 'muk_ai_web_search')
        self.assertEqual(
            body['inputs'][1:],
            [
                {
                    'object': 'entry',
                    'type': 'function.call',
                    'tool_call_id': 'c0',
                    'name': 'muk_ai_web_search',
                    'arguments': '{}',
                },
                {
                    'object': 'entry',
                    'type': 'function.result',
                    'tool_call_id': 'c0',
                    'result': '{"ok": 1}',
                },
                {
                    'object': 'entry',
                    'type': 'message.output',
                    'role': 'assistant',
                    'content': 'ok',
                },
            ],
        )
        self.assertEqual(result['tool_calls'][0]['name'], 'web_search')
        self.assertEqual(
            deltas[0], ('tool_start', {'call_id': 'c1', 'name': 'web_search'})
        )

    def test_connector_output_is_rendered_into_the_answer(self):
        stream = [
            {'type': 'tool.execution.done', 'name': 'web_search', 'info': {}},
            {
                'type': 'tool.execution.done',
                'name': 'code_interpreter',
                'info': {'code': 'print(1)', 'code_output': '1\n'},
            },
            delta('Mistral'),
            delta({'type': 'tool_reference', 'title': 'About', 'url': 'https://m.ai/'}),
            delta({'type': 'tool_file', 'file_id': 'f1', 'file_name': 'cube'}),
            done(),
        ]
        code = '\n\n```python\nprint(1)\n```\n\n```\n1\n```\n\n'
        source = 'Mistral ([About](https://m.ai/))'
        for label, download, image in (
            ('downloaded', None, '![cube](data:image/png;base64,iVBORw0KGgo=)'),
            ('lost', requests.ConnectionError('gone'), '_(generated file: `cube`)_'),
        ):
            answer = json_response({})
            answer._content = PNG
            with (
                self.subTest(file=label),
                patch.object(
                    requests.Session, 'get', side_effect=download, return_value=answer
                ),
            ):
                result, deltas, _sent = self._stream('mistral', stream)
            self.assertEqual(result['text'], f'{code}{source}\n\n{image}'.strip())
            self.assertEqual(''.join(deltas_of(deltas, 'text')).strip(), result['text'])
            self.assertEqual(result['tool_calls'], [])

    def test_an_image_is_drawn_by_the_connector_and_downloaded(self):
        client = self.providers['mistral']._get_client()
        drawn = {
            'type': 'tool.execution',
            'name': 'image_generation',
            'info': {'result': '{"url": "https://blob.test/cube.png?sig=1"}'},
        }
        for label, outputs, error in (
            ('drawn', [drawn, {'type': 'message.output', 'content': '![]()'}], None),
            ('text', [{'type': 'message.output', 'content': 'a cube'}], 'text instead'),
        ):
            answer = json_response({})
            answer._content = PNG
            with (
                self.subTest(answer=label),
                self._capture_post(json_response({'outputs': outputs})) as posts,
                patch.object(requests.Session, 'get', return_value=answer) as get,
            ):
                if error:
                    with self.assertRaisesRegex(UserError, error):
                        client.generate_image('mistral-medium-latest', 'a cube')
                    continue
                image = client.generate_image('mistral-medium-latest', 'a cube')
            self.assertEqual(
                (image['mimetype'], image['data_b64']), ('image/png', 'iVBORw0KGgo=')
            )
            self.assertEqual(get.call_args.args, ('https://blob.test/cube.png?sig=1',))
            self.assertIsNone(get.call_args.kwargs['headers'])
            body = posts[0][1]['json']
            self.assertEqual(body['tools'], [{'type': 'image_generation'}])
            self.assertEqual(posts[0][1]['timeout'], client.provider.image_timeout)
