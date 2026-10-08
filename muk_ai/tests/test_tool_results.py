from __future__ import annotations

import base64
import json
from collections.abc import Iterator
from contextlib import contextmanager, nullcontext
from unittest.mock import patch

from odoo import models
from odoo.tools import BinaryBytes

from odoo.addons.muk_ai.providers import REGISTRY
from odoo.addons.muk_ai.tests.common import (
    PNG_BYTES,
    AITestCommon,
    PNG_1x1,
    serve_web,
    text_payload,
    tool_payload,
)
from odoo.addons.muk_ai.tools.attachment import (
    ATTACHMENT_REF_MAX_BYTES,
    TOOL_VISION_MAX_B64_CHARS,
    TOOL_VISION_MAX_IMAGES,
)
from odoo.addons.muk_mcp.tools.protocol import ToolContent, ToolResult

CSV_BYTES = b'Customer,Revenue\nHarri Stojka,1538.48\n'
XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
PNG_HEADERS = {'Content-Type': 'image/png'}
SHOT = {'data': PNG_1x1, 'mimetype': 'image/png', 'name': 'shot.png'}


def export_result(
    content: bytes = CSV_BYTES,
    mimetype: str = 'text/csv;charset=utf8',
    filename: str = 'res_partner.csv',
) -> dict:
    """Build a result in the shape ``export_records`` returns."""
    return {
        'filename': filename,
        'mimetype': mimetype,
        'row_count': 2,
        'content_base64': base64.b64encode(content).decode(),
    }


class TestToolResults(AITestCommon):
    """Verify what a tool returns reaches the user and the model in usable form."""

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _run(self, name: str, result) -> tuple[models.BaseModel, str, list]:
        """Run a turn whose tool ``name`` answers ``result``.

        :return: the chat, the model-facing output and the provider requests
        """
        session = self._session()
        with (
            self._patch_tool({name: result}),
            self._mock_responses(
                [tool_payload((name, {'model': 'res.partner'}, 'c1')), text_payload()]
            ) as requests,
        ):
            session.start('run the tool')
        return session, self._outputs_for(session, 'c1')[0]['output'], requests

    def _files(self, session: models.BaseModel) -> models.BaseModel:
        """Return the attachments stored on a chat."""
        return self.env['ir.attachment'].search(
            [('res_model', '=', 'muk_ai.session'), ('res_id', '=', session.id)]
        )

    def _images(self, items: list) -> list[dict]:
        """Return the materialized image blocks of the user entries in ``items``."""
        return [
            block
            for item in items
            if item.get('role') == 'user'
            for block in item['content']
            if block.get('strategy') == 'image'
        ]

    def _vision(self, request: dict) -> list[dict]:
        """Return the image blocks a request carries after its last tool output.

        Fails when an image block sits anywhere else in the request.
        """
        inputs = request['inputs']
        last = max(
            index
            for index, item in enumerate(inputs)
            if item.get('type') == 'function_call_output'
        )
        self.assertEqual(self._images(inputs[: last + 1]), [])
        return self._images(inputs[last + 1 :])

    @contextmanager
    def _without_vision(self) -> Iterator[None]:
        """Serve the default provider as one whose models cannot see images."""
        with patch.object(REGISTRY[self.provider.name], 'supports_vision', False):
            self.env.invalidate_all()
            yield
        self.env.invalidate_all()

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_a_file_result_is_stored_and_linked_instead_of_inlined(self):
        session = self._session()
        with (
            self._patch_tool({'export_records': export_result()}),
            self._mock_responses(
                [
                    tool_payload(('export_records', {'model': 'res.partner'}, 'c1')),
                    text_payload('Here is the file.'),
                    text_payload('It lists one customer.'),
                ]
            ) as requests,
        ):
            session.start('export the partners')
            stored = self._tool_output(session, 'c1')
            attachment = self._files(session)
            session.send_message('summarise it', attachment_ids=attachment.ids)
        self.assertEqual(
            stored,
            {
                'filename': 'res_partner.csv',
                'mimetype': 'text/csv',
                'row_count': 2,
                'attachment_id': attachment.id,
                'url': f'/web/content/{attachment.id}?download=1',
            },
        )
        self.assertEqual(
            (attachment.raw.content, attachment.mimetype, attachment.name),
            (CSV_BYTES, 'text/csv', 'res_partner.csv'),
        )
        self.assertIn('<files>', self._system_prompt(requests[0]))
        events = json.dumps(session.fetch_events(limit=1000)['events'])
        self.assertIn(stored['url'], events)
        self.assertNotIn('content_base64', events)
        blocks = [
            block
            for item in requests[2]['inputs']
            if item.get('role') == 'user'
            for block in item['content']
            if block.get('attachment_id') == attachment.id
        ]
        self.assertEqual(blocks[0]['strategy'], 'inline_text')
        self.assertIn('Harri Stojka', blocks[0]['inline_text'])

    def test_a_file_result_of_any_shape_keeps_its_bytes_out_of_the_model(self):
        broken = '{"content_base64": not json}'
        for result, stored, shown in (
            (
                export_result(b'%PDF-1.4 fake', 'application/pdf', 'order.pdf'),
                ('application/pdf', b'%PDF-1.4 fake'),
                '/web/content/',
            ),
            (
                export_result(b'PK fake', XLSX, 'res_partner.xlsx'),
                (XLSX, b'PK fake'),
                '/web/content/',
            ),
            (
                export_result(PNG_BYTES, 'image/png', 'chart.png'),
                ('image/png', PNG_BYTES),
                '/web/image/',
            ),
            (
                export_result(b'x' * 200000),
                ('text/csv', b'x' * 200000),
                '/web/content/',
            ),
            (
                {'filename': 'a.csv', 'mimetype': 'text/csv', 'content_base64': '!!!'},
                None,
                'not valid base64',
            ),
            ({'records': [{'id': 1}], 'length': 1}, None, '"length": 1'),
            ('nothing to see here', None, 'nothing to see here'),
            (broken, None, broken),
        ):
            with self.subTest(result=str(result)[:60]):
                session, output, _requests = self._run('export_records', result)
                files = self._files(session)
                self.assertEqual(
                    [(file.mimetype, file.raw.content) for file in files],
                    [stored] if stored else [],
                )
                self.assertIn(shown, output)
                self.assertLess(len(output), 1000)
                if isinstance(result, dict):
                    self.assertNotIn('content_base64', output)

    def test_a_file_from_an_inline_tool_load_call_is_stored_too(self):
        session = self._session()
        arguments = {
            'names': ['export_records'],
            'call': {'name': 'export_records', 'arguments': {'model': 'res.partner'}},
        }
        with (
            self._patch_tool({'export_records': export_result()}),
            self._mock_responses(
                [tool_payload(('tool_load', arguments, 'c1')), text_payload()]
            ),
        ):
            session.start('export the partners')
        output = self._tool_output(session, 'c1')
        stored = json.loads(output['call']['output'])
        self.assertEqual(self._files(session).ids, [stored['attachment_id']])
        self.assertEqual(self._files(session).raw.content, CSV_BYTES)
        events = json.dumps(session.fetch_events(limit=1000)['events'])
        self.assertIn(stored['url'], events)
        self.assertNotIn('content_base64', events)

    def test_tool_images_reach_the_model_after_every_tool_output(self):
        for client in (False, True):
            with self.subTest(client=client):
                session = self._session()
                calls = [('render', {}, 'c1')]
                if not client:
                    calls.append(('search_count', {'model': 'res.partner'}, 'c2'))
                with (
                    self._as_client_tool('render') if client else nullcontext(),
                    self._patch_tool(
                        {'render': ToolResult(text='Captured', images=[SHOT])}
                    ),
                    self._mock_responses(
                        [tool_payload(*calls), text_payload()]
                    ) as requests,
                ):
                    session.start('show me')
                    if client:
                        session.submit_client_result(
                            'c1', {'text': 'Captured', 'images': [SHOT]}
                        )
                self.assertEqual(session.state, 'done')
                self.assertEqual(
                    self._tool_output(session, 'c1'),
                    {'text': 'Captured'},
                )
                blocks = self._vision(requests[1])
                self.assertEqual(
                    [base64.b64decode(block['data_b64']) for block in blocks],
                    [PNG_BYTES],
                )
                self.assertIn(blocks[0]['attachment_id'], self._files(session).ids)

    def test_tool_images_are_capped_or_explained(self):
        many = [{**SHOT, 'name': f'shot{index}.png'} for index in range(6)]
        blocks = ToolContent(
            [
                {'type': 'text', 'text': 'Captured'},
                {'type': 'image', 'data': PNG_1x1, 'mimeType': 'image/png'},
            ]
        )
        for images, vision, shown in (
            (many, True, TOOL_VISION_MAX_IMAGES),
            ([{**SHOT, 'data': f'data:image/png;base64,{PNG_1x1}'}], True, 1),
            ([{**SHOT, 'data': 'A' * (TOOL_VISION_MAX_B64_CHARS + 1)}], True, 0),
            ([{**SHOT, 'mimetype': 'application/pdf'}], True, 0),
            ([SHOT], False, 0),
            (blocks, True, 1),
            (blocks, False, 0),
        ):
            with (
                self.subTest(images=len(images), vision=vision, shown=shown),
                nullcontext() if vision else self._without_vision(),
            ):
                result = (
                    images
                    if isinstance(images, ToolContent)
                    else ToolResult(text='Captured', images=images)
                )
                _session, output, requests = self._run('render', result)
                blocks = self._vision(requests[1])
                self.assertEqual(
                    {base64.b64decode(block['data_b64']) for block in blocks},
                    {PNG_BYTES} if shown else set(),
                )
                self.assertEqual(len(blocks), shown)
                self.assertNotIn('images', json.loads(output))
                self.assertEqual('cannot be shown' in output, not shown)

    def test_images_inlined_in_an_answer_are_stored_once(self):
        image = f'![chair.png](data:image/png;base64,{PNG_1x1})'
        for text, stored in (('Just text.', 0), (f'A {image} B {image}', 1)):
            with self.subTest(stored=stored):
                session = self._session()
                with self._mock_responses([text_payload(text)]):
                    session.start('draw a chair')
                files = self._files(session)
                self.assertEqual(len(files), stored)
                conversation = json.dumps(session.conversation)
                self.assertNotIn('data:image', session.last_text + conversation)
                if stored:
                    self.assertEqual(
                        (files.raw.content, files.mimetype), (PNG_BYTES, 'image/png')
                    )
                    self.assertEqual(
                        session.last_text.count(f'/web/image/{files.id}'), 2
                    )
                    self.assertIn(f'@attachment:{files.id}', conversation)

    def test_value_references_are_resolved_before_the_tool_runs(self):
        attachments = self.env['ir.attachment']
        png, big, blob = (
            attachments.create(
                {'name': name, 'raw': BinaryBytes(raw), 'mimetype': mimetype}
            )
            for name, raw, mimetype in (
                ('cat.png', PNG_BYTES, 'image/png'),
                ('big.txt', b'a' * (ATTACHMENT_REF_MAX_BYTES + 1), 'text/plain'),
                ('blob.bin', b'\x00\x01', 'application/octet-stream'),
            )
        )
        values = {
            'image': f'@attachment:{png.id}',
            'missing': '@attachment:999999999',
            'big': f'@attachment:{big.id}',
            'blob': f'@attachment:{blob.id}',
            'url': '@url:https://example.com/cat.png',
            'broken': '@url:https://example.com/broken.png',
            'internal': '@url:https://internal.example/cat.png',
            'insecure': '@url:http://example.com/cat.png',
            'plain': 'Hello world',
            'nested': {'gallery': [f'@attachment:{png.id}', 'caption']},
        }
        session = self._session()
        arguments = {'model': 'res.partner.category', 'ids': [1], 'values': values}
        with (
            serve_web(
                {
                    'https://example.com/cat.png': (200, PNG_HEADERS, PNG_BYTES),
                    'https://example.com/broken.png': (500, PNG_HEADERS, b''),
                },
                {'internal.example': ('10.0.0.7',)},
            ),
            self._patch_tool() as calls,
            self._mock_responses(
                [tool_payload(('update_records', arguments, 'c1')), text_payload()]
            ),
        ):
            session.start('set the picture')
        resolved = calls[0]['arguments']['values']
        for key, value in {
            **values,
            'image': PNG_1x1,
            'url': PNG_1x1,
            'nested': {'gallery': [PNG_1x1, 'caption']},
        }.items():
            with self.subTest(key):
                self.assertEqual(resolved[key], value)
        output = self._outputs_for(session, 'c1')[0]['output']
        self.assertEqual(output.count(f'![image set](/web/image/{png.id})'), 2)
        self.assertIn('![image set](https://example.com/cat.png)', output)

    def test_a_tool_output_is_bounded_to_the_context_window(self):
        narrow = self._create_model('narrow-window', context_window=1000)
        agent = self.env['muk_ai.agent'].create(
            {'name': 'Narrow', 'model_id': narrow.id}
        )
        for size, kept in ((900, 900), (1000, 1000), (3000, 1000)):
            with self.subTest(size=size):
                session = self._session(agent_id=agent.id)
                with (
                    self._patch_tool({'search_read': 'x' * size}),
                    self._mock_responses(
                        [
                            tool_payload(
                                ('search_read', {'model': 'res.partner'}, 'c1')
                            ),
                            text_payload(),
                        ]
                    ),
                ):
                    session.start('read everything')
                output = self._outputs_for(session, 'c1')[0]['output']
                self.assertEqual(output.partition('\n')[0], 'x' * kept)
                self.assertEqual(
                    f'{size - kept} of {size} characters dropped' in output,
                    size > kept,
                )
                logged = self._events(session, 'tool_result')[0]['result']
                self.assertEqual(logged, 'x' * size)
