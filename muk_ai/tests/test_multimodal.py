from __future__ import annotations

import base64
import json

from odoo import models
from odoo.exceptions import AccessError, UserError
from odoo.tests import new_test_user

from odoo.addons.muk_ai.tests.common import (
    PNG_BYTES,
    USAGE,
    AITestCommon,
    PNG_1x1,
    sse_response,
    text_payload,
)

PDF_BYTES = (
    b'%PDF-1.4\n%\xe2\xe3\xcf\xd3\n'
    b'1 0 obj<</Type/Catalog>>endobj\n'
    b'trailer<</Root 1 0 R>>\n'
    b'%%EOF\n'
)

INLINE_LIMIT = 256 * 1024

REPLY = [
    {'type': 'response.output_text.delta', 'delta': 'ok'},
    {
        'type': 'response.completed',
        'response': {
            'output': [
                {
                    'type': 'message',
                    'role': 'assistant',
                    'content': [{'type': 'output_text', 'text': 'ok'}],
                }
            ],
            'usage': USAGE,
        },
    },
]


def b64(data: bytes) -> str:
    """Encode ``data`` the way the chat client uploads it."""
    return base64.b64encode(data).decode()


class TestMultimodal(AITestCommon):
    """Verify files a user attaches are stored, checked and handed to the model."""

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _upload(
        self,
        session: models.BaseModel,
        filename: str,
        data: bytes = b'x',
        mimetype: str = 'text/plain',
    ) -> int:
        """Upload ``data`` into ``session`` and return the attachment id."""
        files = [{'filename': filename, 'mimetype': mimetype, 'data_b64': b64(data)}]
        return session.upload_attachments(files)[0]['id']

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_an_upload_is_stored_with_the_way_the_model_reads_it(self):
        session = self._session()
        rows = b'a,b\n1,2\n'
        big = b'x' * (INLINE_LIMIT + 1)
        for filename, mimetype, data, strategy, content in (
            ('pic.png', 'image/png', PNG_BYTES, 'image', PNG_1x1),
            ('doc.pdf', 'application/pdf', PDF_BYTES, 'file', b64(PDF_BYTES)),
            ('rows.csv', 'text/csv', rows, 'inline_text', rows.decode()),
            ('big.txt', 'text/plain', big, 'inline_text', big[:INLINE_LIMIT].decode()),
        ):
            with self.subTest(filename=filename):
                [descriptor] = session.upload_attachments(
                    [
                        {
                            'filename': filename,
                            'mimetype': mimetype,
                            'data_b64': b64(data),
                        }
                    ]
                )
                attachment = self.env['ir.attachment'].browse(descriptor['id'])
                self.assertEqual(
                    descriptor,
                    {
                        'id': attachment.id,
                        'filename': filename,
                        'mimetype': mimetype,
                        'size': len(data),
                    },
                )
                self.assertEqual(attachment.raw.content, data)
                self.assertIn(descriptor, session.get_snapshot()['attachments'])
                block = attachment._ai_materialize()
                self.assertEqual(block['strategy'], strategy)
                self.assertEqual(block.get('data_b64') or block['inline_text'], content)
                self.assertEqual(block.get('truncated', False), data is big)

    def test_an_upload_the_model_cannot_read_is_refused(self):
        self._set_params({'web.max_file_upload_size': 1024})
        session = self._session()
        for filename, mimetype, data_b64, accepted in (
            ('tool.exe', 'application/x-msdownload', b64(b'MZ'), False),
            ('clip.mp4', 'video/mp4', b64(b'\x00'), False),
            ('pic.png', 'image/png', 'not-base64!!!', False),
            ('fits.txt', 'text/plain', b64(b'a' * 1024), True),
            ('over.txt', 'text/plain', b64(b'a' * 1025), False),
        ):
            with self.subTest(filename=filename):
                files = [
                    {'filename': filename, 'mimetype': mimetype, 'data_b64': data_b64}
                ]
                if accepted:
                    self.assertEqual(session.upload_attachments(files)[0]['size'], 1024)
                else:
                    with self.assertRaises(UserError):
                        session.upload_attachments(files)
        self.assertEqual(session.attachment_ids.mapped('name'), ['fits.txt'])

    def test_discard_removes_only_the_uploads_of_the_chat(self):
        session, other = self._session(), self._session()
        kept = self._upload(session, 'kept.txt')
        dropped = self._upload(session, 'dropped.txt')
        foreign = self._upload(other, 'foreign.txt')
        session.discard_attachments([dropped, foreign])
        self.assertEqual(session.attachment_ids.ids, [kept])
        self.assertFalse(self.env['ir.attachment'].browse(dropped).exists())
        self.assertEqual(other.attachment_ids.ids, [foreign])

    def test_only_files_the_sender_may_change_can_be_sent(self):
        owner = new_test_user(self.env, login='attachment-owner')
        stranger = new_test_user(self.env, login='attachment-stranger')
        attachments = self.env['ir.attachment']
        invoice = attachments.create(
            {
                'name': 'invoice.png',
                'raw': PNG_BYTES,
                'mimetype': 'image/png',
                'res_model': 'res.partner',
                'res_id': owner.partner_id.id,
            }
        )
        loose, bundle = attachments.with_user(owner).create(
            [
                {'name': 'loose.png', 'raw': PNG_BYTES, 'mimetype': 'image/png'},
                {'name': 'bundle.zip', 'raw': b'PK', 'mimetype': 'application/zip'},
            ]
        )
        theirs = self._upload(
            self.env['muk_ai.session'].with_user(stranger).create({'name': 'Theirs'}),
            'theirs.txt',
        )
        session = self.env['muk_ai.session'].with_user(owner).create({'name': 'Mine'})
        with self._mock_responses([text_payload()]):
            for attachment_id, error in (
                (invoice.id, UserError),
                (999999999, UserError),
                (bundle.id, UserError),
                (theirs, AccessError),
                (loose.id, None),
            ):
                with self.subTest(attachment_id=attachment_id):
                    if error:
                        with self.assertRaises(error):
                            session.send_message('', attachment_ids=[attachment_id])
                        self.assertFalse(session.conversation)
                    else:
                        session.send_message('', attachment_ids=[attachment_id])
        self.assertEqual(invoice.res_model, 'res.partner')
        self.assertEqual(
            (loose.res_model, loose.res_id), ('muk_ai.session', session.id)
        )
        self.assertEqual(
            session.conversation[0]['content'],
            [
                {
                    'type': 'input_text',
                    'text': f'Attached file loose.png: odoo://attachment/{loose.id}',
                },
                {
                    'type': 'muk_ai_attachment',
                    'attachment_id': loose.id,
                    'filename': 'loose.png',
                    'mimetype': 'image/png',
                },
            ],
        )

    def test_an_attachment_reaches_the_vendor_with_its_content(self):
        session = self._session()
        image = self._upload(session, 'pic.png', PNG_BYTES, 'image/png')
        with self._capture_post(sse_response(REPLY), sse_response(REPLY)) as posts:
            session.send_message('Describe this', attachment_ids=[image])
            stored = json.dumps(session.conversation)
            [event] = self._events(session, 'user_message')
            session.discard_attachments([image])
            session.send_message('And now?')
        self.assertEqual(session.state, 'done')
        self.assertIn(f'"attachment_id": {image}', stored)
        self.assertNotIn(PNG_1x1, stored)
        self.assertEqual([file['id'] for file in event['attachments']], [image])
        first, second = (json.dumps(kwargs['json']) for _url, kwargs in posts)
        self.assertIn(PNG_1x1, first)
        self.assertNotIn(PNG_1x1, second)
        self.assertIn('[Missing: pic.png]', second)
