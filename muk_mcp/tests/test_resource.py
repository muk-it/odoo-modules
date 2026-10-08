from __future__ import annotations

import base64
import io
from unittest.mock import patch

from openpyxl import Workbook
from reportlab.pdfgen import canvas

from odoo import models
from odoo.exceptions import AccessError, UserError
from odoo.tests import new_test_user
from odoo.tools import BinaryBytes

from odoo.addons.muk_mcp.tests.common import MCPToolCase

PNG = (
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQ'
    'VQYV2NgAAIAAAUAAarVyFEAAAAASUVORK5CYII='
)
XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'


def build_pdf(text: str) -> bytes:
    """Render a one-page PDF containing ``text``."""
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.drawString(72, 720, text)
    pdf.save()
    return buffer.getvalue()


def build_xlsx(text: str) -> bytes:
    """Build a workbook whose first cell holds ``text``."""
    buffer = io.BytesIO()
    workbook = Workbook()
    workbook.active['A1'] = text
    workbook.save(buffer)
    return buffer.getvalue()


class TestMcpReadResource(MCPToolCase):
    """Cover the ``read_resource`` tool on attachment and record-field URIs."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        """Create the partner owning every attachment."""
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({'name': 'MCP Resource Owner'})

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _attach(self, name: str, mimetype: str, data: bytes) -> models.BaseModel:
        """Attach ``data`` to the test partner."""
        return self.env['ir.attachment'].create(
            {
                'name': name,
                'mimetype': mimetype,
                'raw': BinaryBytes(data),
                'res_model': 'res.partner',
                'res_id': self.partner.id,
            },
        )

    def _read(self, attachment: models.BaseModel, **kwargs: str) -> list[dict]:
        """Read ``attachment`` through the tool and return its content blocks."""
        return self.call_tool(
            'read_resource',
            {'uri': f'odoo://attachment/{attachment.id}', **kwargs},
        )

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_inline_mimetypes_become_typed_blocks(self):
        for name, mimetype, data, kind in (
            ('notes.txt', 'text/plain', b'hello', 'text'),
            ('notes.txt', 'text/plain; charset=utf-8', b'hello', 'text'),
            ('config.json', 'application/json', b'{"k": 1}', 'text'),
            ('icon.svg', 'image/svg+xml', b'<svg/>', 'text'),
            ('pic.png', 'image/png', bytes(range(64)), 'image'),
            ('clip.wav', 'audio/wav', bytes(range(32)), 'audio'),
            ('broken.txt', 'text/plain', b'\xff\xfe\x00bad', 'resource'),
            ('blob.bin', 'application/octet-stream', b'\x00' * 8, 'resource'),
            ('guide.md', 'application/octet-stream', b'# Guide\n\nRead me.', 'text'),
        ):
            with self.subTest(mimetype=mimetype, data=data):
                attachment = self._attach(name, mimetype, data)
                [block] = self._read(attachment, format='resource')
                self.assertEqual(block['type'], kind)
                if kind == 'text':
                    self.assertEqual(block['text'], data.decode())
                elif kind == 'resource':
                    resource = block['resource']
                    self.assertEqual(
                        resource['uri'], f'odoo://attachment/{attachment.id}'
                    )
                    self.assertEqual(resource['name'], name)
                    self.assertEqual(base64.b64decode(resource['blob']), data)
                else:
                    self.assertEqual(block['mimeType'], mimetype)
                    self.assertEqual(base64.b64decode(block['data']), data)

    def test_indexable_documents_honour_the_format(self):
        pdf = self._attach('greet.pdf', 'application/pdf', build_pdf('Hello PDF'))
        sheet = self._attach('sheet.xlsx', XLSX, build_xlsx('Hello XLSX'))
        broken = self._attach('broken.pdf', 'application/pdf', b'%PDF-1.4\n%broken')
        for attachment, text, format_, kinds in (
            (pdf, 'Hello PDF', 'auto', ['text', 'resource']),
            (pdf, 'Hello PDF', 'text', ['text']),
            (pdf, None, 'resource', ['resource']),
            (sheet, 'Hello XLSX', 'auto', ['text', 'resource']),
            (broken, None, 'auto', ['resource']),
        ):
            with self.subTest(name=attachment.name, format=format_):
                blocks = self._read(attachment, format=format_)
                self.assertEqual([block['type'] for block in blocks], kinds)
                if text:
                    self.assertIn(text, blocks[0]['text'])
                if 'resource' in kinds:
                    self.assertEqual(
                        base64.b64decode(blocks[-1]['resource']['blob']),
                        attachment.raw.content,
                    )
        for format_ in ('text', 'bogus'):
            with self.subTest(format=format_), self.assertRaises(UserError):
                self._read(broken, format=format_)

    def test_record_binary_fields_are_readable(self):
        self.partner.image_1920 = PNG
        [block] = self.call_tool(
            'read_resource',
            {'uri': f'ODOO://record/res.partner/{self.partner.id}/image_1920?x=1'},
        )
        self.assertEqual(block['type'], 'image')
        self.assertEqual(
            base64.b64decode(block['data']), self.partner.image_1920.content
        )

    def test_unresolvable_uris_raise(self):
        partner = self.partner.id
        for uri in (
            'odoo://attachment/999999999',
            'odoo://attachment/abc',
            'odoo://attachment/1/2',
            'odoo://Attachment/1',
            'https://example.com/file.png',
            'not a uri',
            f'odoo://record/res.partner/{partner}',
            'odoo://record/res.partner/abc/image_1920',
            f'odoo://record/res.partner/{partner}/no_such_field',
            f'odoo://record/res.partner/{partner}/name',
            f'odoo://record/res.partner/{partner}/image_1920',
            'odoo://record/res.partner/999999999/image_1920',
            'odoo://record/no.such.model/1/x',
        ):
            with self.subTest(uri), self.assertRaises(UserError):
                self.call_tool('read_resource', {'uri': uri})

    def test_field_groups_guard_record_binary_fields(self):
        self.partner.image_1920 = PNG
        user = new_test_user(self.env, login='mcp_resource_user')
        uri = f'odoo://record/res.partner/{self.partner.id}/image_1920'
        field = self.env['res.partner']._fields['image_1920']
        with (
            patch.object(field, 'groups', 'base.group_system'),
            self.assertRaises(AccessError),
        ):
            self.call_tool('read_resource', {'uri': uri}, user=user)
        [block] = self.call_tool('read_resource', {'uri': uri}, user=user)
        self.assertEqual(block['type'], 'image')
