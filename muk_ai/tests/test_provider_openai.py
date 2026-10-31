import base64
from unittest.mock import patch

import requests

from odoo.exceptions import UserError
from odoo.tools import mute_logger

from odoo.addons.muk_ai.tests.common import PNG_BYTES, PNG_1x1, json_response
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

    def test_the_sandbox_gets_the_chat_files_and_deletes_them_after(self):
        attached = {
            'type': 'muk_ai_attachment',
            'attachment_id': 7,
            'filename': 'list.csv',
            'mimetype': 'text/csv',
            'strategy': 'inline_text',
            'inline_text': 'a,b',
            'data_b64': 'YSxi',
        }
        for label, uploaded, files in (
            ('uploaded', json_response({'id': 'file-1'}), ['file-1']),
            ('refused', json_response({}, 404), []),
        ):
            with (
                self.subTest(upload=label),
                patch.object(requests.Session, 'delete') as deleted,
            ):
                _result, _deltas, sent = self._stream(
                    'openai',
                    uploaded,
                    [openai_event('output_text.delta', delta='ok'), openai_end()],
                    inputs=[{'role': 'user', 'content': [attached]}],
                    enable_code_interpreter=True,
                )
            self.assertEqual(
                (sent[0]['data'], sent[0]['files']['file'][:2]),
                ({'purpose': 'user_data'}, ('list.csv', b'a,b')),
            )
            body = sent[1]['json']
            self.assertEqual(
                body['tools'][-1]['container'], {'type': 'auto', 'file_ids': files}
            )
            self.assertEqual(body['input'][0]['content'][0]['type'], 'input_text')
            self.assertEqual(
                [call.args[0].rsplit('/', 1)[-1] for call in deleted.call_args_list],
                files,
            )

    def test_files_the_sandbox_cites_are_inlined_as_data(self):
        def cited(text: str, *refs: str) -> dict:
            """Build an answer citing each sandbox file ``refs`` names."""
            message = openai_message(text)
            message['content'][0]['annotations'] = [
                {
                    'type': 'container_file_citation',
                    'container_id': 'cntr_1',
                    'file_id': f'cfile_{ref}',
                    'filename': ref,
                    'start_index': text.index(f'sandbox:/mnt/data/{ref}'),
                    'end_index': text.index(f'sandbox:/mnt/data/{ref}')
                    + len(f'sandbox:/mnt/data/{ref}'),
                }
                for ref in refs
            ]
            return message

        def get(url: str, **_kwargs) -> requests.Response:
            """Answer a container file download with its content."""
            answer = json_response({})
            answer._content = PNG_BYTES if 'c.png' in url else b'a,b\n1,2\n'
            return answer

        csv = base64.b64encode(b'a,b\n1,2\n').decode()
        png = base64.b64encode(PNG_BYTES).decode()
        for label, message, download, text in (
            (
                'linked and bare',
                cited(
                    'Here: [the list](sandbox:/mnt/data/p.csv), also '
                    'sandbox:/mnt/data/p.csv and [a plot](sandbox:/mnt/data/c.png).',
                    'p.csv',
                    'c.png',
                ),
                None,
                (
                    f'Here: [the list](data:text/csv;base64,{csv}), also '
                    f'[p.csv](data:text/csv;base64,{csv}) and '
                    f'![a plot](data:image/png;base64,{png}).'
                ),
            ),
            (
                'lost',
                cited('[the list](sandbox:/mnt/data/p.csv)', 'p.csv'),
                requests.ConnectionError('gone'),
                '[the list](sandbox:/mnt/data/p.csv)',
            ),
        ):
            with (
                self.subTest(files=label),
                patch.object(
                    requests.Session, 'get', side_effect=download or get
                ) as fetched,
            ):
                result, _deltas, _sent = self._stream(
                    'openai',
                    [
                        openai_event(
                            'output_text.delta', delta=message['content'][0]['text']
                        ),
                        openai_end(message),
                    ],
                )
            self.assertEqual(result['text'], text)
            self.assertEqual(result['carry_inputs'][-1]['content'][0]['text'], text)
            self.assertIn(
                '/containers/cntr_1/files/cfile_p.csv/content',
                fetched.call_args_list[0].args[0],
            )

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
