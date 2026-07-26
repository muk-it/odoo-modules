from __future__ import annotations

import base64
import io

from PIL import Image

from odoo import models
from odoo.exceptions import UserError

from odoo.addons.muk_ai.models import ir_attachment as ir_att
from odoo.addons.muk_ai.providers.anthropic import AnthropicProvider
from odoo.addons.muk_ai.providers.openai import OpenAIProvider
from odoo.addons.muk_ai.tests.common import AITestCommon


def _tiny_png() -> bytes:
    """Return the raw bytes of a 1x1 red PNG image."""
    buffer = io.BytesIO()
    Image.new('RGB', (1, 1), (255, 0, 0)).save(buffer, format='PNG')
    return buffer.getvalue()


PNG_BYTES = _tiny_png()

PDF_BYTES = (
    b'%PDF-1.4\n%\xe2\xe3\xcf\xd3\n'
    b'1 0 obj<</Type/Catalog>>endobj\n'
    b'trailer<</Root 1 0 R>>\n'
    b'%%EOF\n'
)


class TestMultimodalAttachments(AITestCommon):
    """Verify multimodal attachment handling across providers."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.session = cls.env['muk_ai.session'].create({'name': 'Multimodal'})

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _make_attachment(
        self, filename: str, mimetype: str, raw: bytes
    ) -> models.BaseModel:
        """Attach the raw bytes to the session under test."""
        return self.env['ir.attachment'].create(
            {
                'name': filename,
                'datas': base64.b64encode(raw),
                'mimetype': mimetype,
                'res_model': 'muk_ai.session',
                'res_id': self.session.id,
            }
        )

    # ----------------------------------------------------------
    # Tests: mimetype / size validation
    # ----------------------------------------------------------

    def test_reject_unknown_mimetype(self):
        with self.assertRaises(UserError):
            self.env['ir.attachment']._ai_check_mimetype('application/x-malware')

    def test_reject_oversize(self):
        self.env['ir.config_parameter'].sudo().set_param(
            'web.max_file_upload_size',
            str(1024 * 1024),
        )
        with self.assertRaises(UserError):
            self.env['ir.attachment']._ai_check_size(2 * 1024 * 1024)

    def test_strategy_detection(self):
        Attachment = self.env['ir.attachment']
        self.assertEqual(Attachment._ai_strategy_for('image/png'), 'image')
        self.assertEqual(Attachment._ai_strategy_for('image/jpeg'), 'image')
        self.assertEqual(Attachment._ai_strategy_for('application/pdf'), 'file')
        self.assertEqual(Attachment._ai_strategy_for('text/plain'), 'inline_text')
        self.assertIsNone(Attachment._ai_strategy_for('video/mp4'))

    # ----------------------------------------------------------
    # Tests: materialize
    # ----------------------------------------------------------

    def test_materialize_image(self):
        attachment = self._make_attachment('logo.png', 'image/png', PNG_BYTES)
        block = attachment._ai_materialize()
        self.assertEqual(block['type'], 'muk_ai_attachment')
        self.assertEqual(block['strategy'], 'image')
        self.assertEqual(block['mimetype'], 'image/png')
        self.assertEqual(
            base64.b64decode(block['data_b64']),
            PNG_BYTES,
        )
        self.assertNotIn('inline_text', block)

    def test_materialize_pdf(self):
        attachment = self._make_attachment('doc.pdf', 'application/pdf', PDF_BYTES)
        block = attachment._ai_materialize()
        self.assertEqual(block['strategy'], 'file')
        self.assertEqual(
            base64.b64decode(block['data_b64']),
            PDF_BYTES,
        )

    def test_materialize_text_inline(self):
        raw = b'Hello from a tiny csv\nline,2'
        attachment = self._make_attachment('sample.csv', 'text/csv', raw)
        block = attachment._ai_materialize()
        self.assertEqual(block['strategy'], 'inline_text')
        self.assertEqual(block['inline_text'], raw.decode('utf-8'))
        self.assertFalse(block['truncated'])

    def test_materialize_text_truncated(self):
        original = ir_att.DEFAULT_TEXT_INLINE_LIMIT_KB
        ir_att.DEFAULT_TEXT_INLINE_LIMIT_KB = 1
        self.addCleanup(setattr, ir_att, 'DEFAULT_TEXT_INLINE_LIMIT_KB', original)
        raw = ('x' * 2048).encode('utf-8')
        attachment = self._make_attachment('big.txt', 'text/plain', raw)
        block = attachment._ai_materialize()
        self.assertTrue(block['truncated'])
        self.assertEqual(len(block['inline_text']), 1024)

    # ----------------------------------------------------------
    # Tests: upload and discard
    # ----------------------------------------------------------

    def test_upload_attachments(self):
        descriptors = self.session.upload_attachments(
            [
                {
                    'filename': 'pic.png',
                    'mimetype': 'image/png',
                    'data_b64': base64.b64encode(PNG_BYTES).decode('ascii'),
                }
            ]
        )
        self.assertEqual(len(descriptors), 1)
        self.assertEqual(descriptors[0]['filename'], 'pic.png')
        self.assertEqual(descriptors[0]['mimetype'], 'image/png')
        self.assertTrue(descriptors[0]['id'])
        self.assertIn(
            descriptors[0]['id'],
            self.session.attachment_ids.ids,
        )
        attachment = self.env['ir.attachment'].browse(descriptors[0]['id'])
        self.assertEqual(attachment.res_model, 'muk_ai.session')
        self.assertEqual(attachment.res_id, self.session.id)

    def test_action_upload_rejects_bad_mimetype(self):
        with self.assertRaises(UserError):
            self.session.upload_attachments(
                [
                    {
                        'filename': 'nope.exe',
                        'mimetype': 'application/x-msdownload',
                        'data_b64': base64.b64encode(b'MZ').decode('ascii'),
                    }
                ]
            )

    def test_action_upload_rejects_bad_base64(self):
        with self.assertRaises(UserError):
            self.session.upload_attachments(
                [
                    {
                        'filename': 'x.png',
                        'mimetype': 'image/png',
                        'data_b64': 'not-base64!!!',
                    }
                ]
            )

    def test_discard_attachments(self):
        descriptors = self.session.upload_attachments(
            [
                {
                    'filename': 'pic.png',
                    'mimetype': 'image/png',
                    'data_b64': base64.b64encode(PNG_BYTES).decode('ascii'),
                }
            ]
        )
        attachment_id = descriptors[0]['id']
        self.session.discard_attachments([attachment_id])
        self.assertNotIn(attachment_id, self.session.attachment_ids.ids)
        self.assertFalse(
            self.env['ir.attachment'].browse(attachment_id).exists(),
        )

    def test_unlink_session_cleans_attachments(self):
        session = self.env['muk_ai.session'].create({'name': 'Disposable'})
        descriptors = session.upload_attachments(
            [
                {
                    'filename': 'pic.png',
                    'mimetype': 'image/png',
                    'data_b64': base64.b64encode(PNG_BYTES).decode('ascii'),
                }
            ]
        )
        attachment_id = descriptors[0]['id']
        session.unlink()
        self.assertFalse(
            self.env['ir.attachment'].browse(attachment_id).exists(),
        )

    # ----------------------------------------------------------
    # Tests: session send flow
    # ----------------------------------------------------------

    def test_send_message_carries_attachment(self):
        session = self.env['muk_ai.session'].create({'name': 'Send'})
        attachment = self._make_attachment('pic.png', 'image/png', PNG_BYTES)
        with self._mock_responses([self._make_text_response('done')]):
            session.start('Describe this', attachment_ids=[attachment.id])
        user_entries = [
            item for item in session.conversation or [] if item.get('role') == 'user'
        ]
        self.assertTrue(user_entries)
        blocks = user_entries[0]['content']
        text_blocks = [b for b in blocks if b['type'] == 'input_text']
        attachment_blocks = [b for b in blocks if b['type'] == 'muk_ai_attachment']
        self.assertEqual(len(text_blocks), 1)
        self.assertEqual(text_blocks[0]['text'], 'Describe this')
        self.assertEqual(len(attachment_blocks), 1)
        self.assertEqual(attachment_blocks[0]['attachment_id'], attachment.id)
        self.assertIn(attachment, session.attachment_ids)
        event_users = [
            e
            for e in session.fetch_events(limit=500)['events']
            if e.get('kind') == 'user_message'
        ]
        self.assertEqual(len(event_users), 1)
        self.assertEqual(len(event_users[0]['attachments']), 1)
        self.assertEqual(
            event_users[0]['attachments'][0]['id'],
            attachment.id,
        )

    def test_send_message_attachment_only(self):
        session = self.env['muk_ai.session'].create({'name': 'Attach-only'})
        attachment = self._make_attachment('pic.png', 'image/png', PNG_BYTES)
        with self._mock_responses([self._make_text_response('done')]):
            session.start(None, attachment_ids=[attachment.id])
        user_entries = [
            item for item in session.conversation or [] if item.get('role') == 'user'
        ]
        self.assertEqual(len(user_entries), 1)
        blocks = user_entries[0]['content']
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0]['type'], 'muk_ai_attachment')

    def test_resolve_rejects_unrelated_ids(self):
        session = self.env['muk_ai.session'].create({'name': 'Resolve'})
        with self.assertRaises(UserError):
            session._resolve_attachments([999999999])

    def test_resolve_rejects_foreign_attachment(self):
        session = self.env['muk_ai.session'].create({'name': 'Foreign'})
        foreign = self.env['ir.attachment'].create(
            {
                'name': 'invoice.png',
                'datas': base64.b64encode(PNG_BYTES),
                'mimetype': 'image/png',
                'res_model': 'res.partner',
                'res_id': self.env.user.partner_id.id,
            }
        )
        with self.assertRaises(UserError):
            session._resolve_attachments([foreign.id])
        self.assertEqual(foreign.res_model, 'res.partner')

    # ----------------------------------------------------------
    # Tests: provider dispatcher materialization
    # ----------------------------------------------------------

    def test_provider_materializes_attachment_blocks(self):
        attachment = self._make_attachment('pic.png', 'image/png', PNG_BYTES)
        inputs = [
            {
                'role': 'user',
                'content': [
                    {'type': 'input_text', 'text': 'look'},
                    {
                        'type': 'muk_ai_attachment',
                        'attachment_id': attachment.id,
                        'filename': 'pic.png',
                        'mimetype': 'image/png',
                    },
                ],
            }
        ]
        materialized = self.provider._materialize_inputs(inputs)
        blocks = materialized[0]['content']
        self.assertEqual(blocks[0]['type'], 'input_text')
        self.assertEqual(blocks[1]['type'], 'muk_ai_attachment')
        self.assertEqual(blocks[1]['strategy'], 'image')
        self.assertEqual(
            base64.b64decode(blocks[1]['data_b64']),
            PNG_BYTES,
        )

    def test_provider_handles_missing_attachment(self):
        inputs = [
            {
                'role': 'user',
                'content': [
                    {
                        'type': 'muk_ai_attachment',
                        'attachment_id': 999999999,
                        'filename': 'gone.png',
                        'mimetype': 'image/png',
                    }
                ],
            }
        ]
        materialized = self.provider._materialize_inputs(inputs)
        block = materialized[0]['content'][0]
        self.assertEqual(block['type'], 'input_text')
        self.assertIn('Missing', block['text'])
        self.assertIn('gone.png', block['text'])

    # ----------------------------------------------------------
    # Tests: provider adapters OpenAI
    # ----------------------------------------------------------

    def test_openai_rewrite_image(self):
        inputs = [
            {
                'role': 'user',
                'content': [
                    {
                        'type': 'muk_ai_attachment',
                        'strategy': 'image',
                        'mimetype': 'image/png',
                        'data_b64': 'AAAA',
                    }
                ],
            }
        ]
        rewritten = OpenAIProvider._rewrite_attachments(inputs)
        block = rewritten[0]['content'][0]
        self.assertEqual(block['type'], 'input_image')
        self.assertEqual(block['image_url'], 'data:image/png;base64,AAAA')

    def test_openai_rewrite_pdf(self):
        inputs = [
            {
                'role': 'user',
                'content': [
                    {
                        'type': 'muk_ai_attachment',
                        'strategy': 'file',
                        'mimetype': 'application/pdf',
                        'filename': 'doc.pdf',
                        'data_b64': 'AAAA',
                    }
                ],
            }
        ]
        rewritten = OpenAIProvider._rewrite_attachments(inputs)
        block = rewritten[0]['content'][0]
        self.assertEqual(block['type'], 'input_file')
        self.assertEqual(block['filename'], 'doc.pdf')
        self.assertEqual(block['file_data'], 'data:application/pdf;base64,AAAA')

    def test_openai_rewrite_inline_text(self):
        inputs = [
            {
                'role': 'user',
                'content': [
                    {
                        'type': 'muk_ai_attachment',
                        'strategy': 'inline_text',
                        'mimetype': 'text/plain',
                        'filename': 'note.txt',
                        'inline_text': 'hello',
                        'truncated': False,
                    }
                ],
            }
        ]
        rewritten = OpenAIProvider._rewrite_attachments(inputs)
        block = rewritten[0]['content'][0]
        self.assertEqual(block['type'], 'input_text')
        self.assertIn('note.txt', block['text'])
        self.assertIn('hello', block['text'])

    # ----------------------------------------------------------
    # Tests: provider adapters Anthropic
    # ----------------------------------------------------------

    def test_anthropic_rewrite_image(self):
        inputs = [
            {
                'role': 'user',
                'content': [
                    {
                        'type': 'muk_ai_attachment',
                        'strategy': 'image',
                        'mimetype': 'image/jpeg',
                        'data_b64': 'AAAA',
                    }
                ],
            }
        ]
        _, messages, _anchor = AnthropicProvider._inputs_to_messages(inputs)
        block = messages[0]['content'][0]
        self.assertEqual(block['type'], 'image')
        self.assertEqual(block['source']['type'], 'base64')
        self.assertEqual(block['source']['media_type'], 'image/jpeg')
        self.assertEqual(block['source']['data'], 'AAAA')

    def test_anthropic_rewrite_pdf(self):
        inputs = [
            {
                'role': 'user',
                'content': [
                    {
                        'type': 'muk_ai_attachment',
                        'strategy': 'file',
                        'mimetype': 'application/pdf',
                        'data_b64': 'AAAA',
                    }
                ],
            }
        ]
        _, messages, _anchor = AnthropicProvider._inputs_to_messages(inputs)
        block = messages[0]['content'][0]
        self.assertEqual(block['type'], 'document')
        self.assertEqual(block['source']['media_type'], 'application/pdf')

    def test_anthropic_rewrite_inline_text(self):
        inputs = [
            {
                'role': 'user',
                'content': [
                    {
                        'type': 'muk_ai_attachment',
                        'strategy': 'inline_text',
                        'mimetype': 'text/markdown',
                        'filename': 'note.md',
                        'inline_text': '# header\nhi',
                        'truncated': True,
                    }
                ],
            }
        ]
        _, messages, _anchor = AnthropicProvider._inputs_to_messages(inputs)
        block = messages[0]['content'][0]
        self.assertEqual(block['type'], 'text')
        self.assertIn('note.md', block['text'])
        self.assertIn('# header', block['text'])
        self.assertIn('[truncated]', block['text'])
