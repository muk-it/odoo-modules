import requests

from odoo.exceptions import UserError
from odoo.tools import mute_logger

from odoo.addons.muk_ai.tests.common import PNG_1x1, json_response
from odoo.addons.muk_ai.tests.providers import (
    TOOLS,
    USER,
    ProviderTestCase,
    deltas_of,
    openai_end,
    openai_event,
    openai_message,
)


class TestOpenAIProvider(ProviderTestCase):
    """Verify the OpenAI-only parts of the Responses wire and the image endpoint."""

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_the_request_carries_the_responses_extras(self):
        for kwargs, expected in (
            (
                {'cache_key': 'muk_ai.session:42'},
                {'prompt_cache_key': 'muk_ai.session:42', 'store': False},
            ),
            ({}, {'prompt_cache_key': None, 'parallel_tool_calls': None}),
            ({'tools_schema': TOOLS}, {'parallel_tool_calls': True}),
            (
                {'model': 'gpt-5.4-mini'},
                {
                    'reasoning': {'summary': 'detailed', 'effort': 'medium'},
                    'include': ['reasoning.encrypted_content'],
                },
            ),
            ({'model': 'gpt-4o'}, {'reasoning': None, 'include': None}),
        ):
            with self.subTest(request=kwargs):
                _result, _deltas, sent = self._stream(
                    'openai', [openai_end()], **kwargs
                )
                body = sent[0]['json']
                self.assertEqual({key: body.get(key) for key in expected}, expected)

    def test_reasoning_items_are_carried_once_and_replayed(self):
        reasoning = {'type': 'reasoning', 'id': 'rs_1', 'encrypted_content': 'enc'}
        for events, carried, truncated in (
            (
                [
                    openai_event('output_item.done', item=reasoning),
                    openai_event('output_text.delta', delta='ok'),
                    openai_end(reasoning, openai_message('ok')),
                ],
                [reasoning, openai_message('ok')],
                False,
            ),
            (
                [
                    openai_end(
                        reasoning,
                        kind='incomplete',
                        incomplete_details={'reason': 'max_output_tokens'},
                    )
                ],
                [reasoning],
                True,
            ),
        ):
            with self.subTest(truncated=truncated):
                result, _deltas, _sent = self._stream('openai', events)
                self.assertEqual(result['carry_inputs'], carried)
                self.assertEqual('Max Tokens' in result['text'], truncated)
                _result, _deltas, sent = self._stream(
                    'openai', [openai_end()], inputs=[USER, *carried, USER]
                )
                self.assertEqual(sent[0]['json']['input'][1:-1], carried)

    def test_code_interpreter_calls_render_once_as_markdown(self):
        call = {
            'type': 'code_interpreter_call',
            'id': 'ci1',
            'code': 'print(1)\n',
            'results': [
                {'type': 'logs', 'logs': '1\n'},
                {'type': 'files', 'files': [{'name': 'plot.png'}]},
            ],
        }
        rendered = (
            '```python\nprint(1)\n```\n\n```\n1\n```\n\n_(generated file: `plot.png`)_'
        )
        for label, events in (
            ('item done', [openai_event('output_item.done', item=call), openai_end()]),
            ('completed', [openai_end(call)]),
            ('both', [openai_event('output_item.done', item=call), openai_end(call)]),
        ):
            with self.subTest(event=label):
                result, deltas, _sent = self._stream('openai', events)
                self.assertEqual(result['text'], rendered)
                self.assertEqual(''.join(deltas_of(deltas, 'text')).strip(), rendered)

    @mute_logger('odoo.addons.muk_ai.providers.base')
    def test_a_rejected_summary_drops_the_reasoning_config_entirely(self):
        rejected = {'message': 'Organization must be verified for reasoning summaries.'}
        result, _deltas, sent = self._stream(
            'openai',
            json_response({'error': rejected}, 400),
            json_response({'error': rejected}, 400),
            [openai_event('output_text.delta', delta='ok'), openai_end()],
            model='gpt-5.4-mini',
            reasoning_effort='low',
        )
        self.assertEqual(
            [
                (record['json'].get('reasoning'), 'include' in record['json'])
                for record in sent
            ],
            [
                ({'summary': 'detailed', 'effort': 'low'}, True),
                ({'summary': 'detailed'}, True),
                (None, False),
            ],
        )
        self.assertEqual(result['text'], 'ok')

    def test_images_render_through_the_generations_endpoint(self):
        self.providers['openai'].write({'request_timeout': 60, 'image_timeout': 300})
        for model, options, body in (
            (
                'gpt-image-2',
                {'size': '1024x1024', 'quality': None},
                {'model': 'gpt-image-2', 'prompt': 'a dot', 'size': '1024x1024'},
            ),
            (
                'dall-e-3',
                None,
                {'model': 'dall-e-3', 'prompt': 'a dot', 'response_format': 'b64_json'},
            ),
        ):
            with self.subTest(model=model):
                image = {'b64_json': PNG_1x1, 'revised_prompt': 'a red dot'}
                with self._wire(json_response({'data': [image]})) as sent:
                    result = (
                        self.providers['openai']
                        ._get_client()
                        .generate_image(model, 'a dot', options)
                    )
                self.assertTrue(sent[0]['url'].endswith('/images/generations'))
                self.assertEqual((sent[0]['json'], sent[0]['timeout']), (body, 300))
                self.assertEqual(
                    result,
                    {
                        'data_b64': PNG_1x1,
                        'mimetype': 'image/png',
                        'revised_prompt': 'a red dot',
                        'usage': {'images': 1},
                    },
                )

    def test_a_failed_image_render_raises_a_user_error(self):
        missing = json_response({}, 404)
        missing._content, missing.reason = b'', 'Not Found'
        for name, answer, message in (
            (
                'openai',
                json_response(
                    {'error': {'message': 'gpt-image-99 does not exist'}}, 400
                ),
                'gpt-image-99 does not exist',
            ),
            ('anthropic', missing, '404 Client Error: Not Found'),
            ('openai', json_response({'data': []}), 'no image data returned'),
            ('openai', requests.ConnectionError('connection refused'), 'refused'),
        ):
            with (
                self.subTest(provider=name, failure=message),
                self._wire(answer),
                self.assertRaisesRegex(UserError, message),
            ):
                self.providers[name]._get_client().generate_image(
                    'gpt-image-99', 'a dot'
                )
