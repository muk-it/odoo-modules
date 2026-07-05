import base64
import io

from openpyxl import Workbook
from reportlab.pdfgen import canvas

from odoo.exceptions import AccessError, UserError
from odoo.tests import common, tagged
from odoo.tests.common import new_test_user

from odoo.addons.muk_mcp.tools.protocol import ToolContent


@tagged('post_install', '-at_install')
class TestReadResource(common.TransactionCase):
    """Verify content-block resolution for attachment and record-field URIs."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tool_model = cls.env['muk_mcp.tool']
        cls.mixin = cls.env['muk_mcp.mixin']
        cls.partner = cls.env['res.partner'].create({'name': 'Att Owner'})
        png_b64 = (
            b'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQ'
            b'VQYV2NgAAIAAAUAAarVyFEAAAAASUVORK5CYII='
        )
        cls.acl_partner = cls.env['res.partner'].create(
            {
                'name': 'Confidential Owner',
                'image_1920': png_b64,
            },
        )
        cls.acl_user = new_test_user(
            cls.env,
            login='mcp_field_acl_user',
            groups='base.group_user',
        )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _call(self, uri):
        result, _info = self.tool_model._call(
            'read_resource',
            {'uri': uri},
            self.env,
        )
        self.assertIsInstance(result, ToolContent)
        self.assertEqual(len(result), 1)
        return result[0]

    def _call_raw(self, uri, **kwargs):
        payload = {'uri': uri, **kwargs}
        result, _info = self.tool_model._call(
            'read_resource',
            payload,
            self.env,
        )
        self.assertIsInstance(result, ToolContent)
        return result

    def _make_attachment(self, name, mimetype, raw_bytes):
        return self.env['ir.attachment'].create(
            {
                'name': name,
                'mimetype': mimetype,
                'datas': base64.b64encode(raw_bytes).decode('ascii'),
                'res_model': 'res.partner',
                'res_id': self.partner.id,
            },
        )

    def _attachment_uri(self, attachment):
        return 'odoo://attachment/%d' % attachment.id

    def _build_pdf(self, text='Hello PDF World'):
        buf = io.BytesIO()
        c = canvas.Canvas(buf)
        c.drawString(72, 720, text)
        c.save()
        return buf.getvalue()

    def _build_xlsx(self, text='Hello XLSX World'):
        buf = io.BytesIO()
        wb = Workbook()
        ws = wb.active
        ws['A1'] = text
        wb.save(buf)
        return buf.getvalue()

    # ----------------------------------------------------------
    # Tests — attachment uri
    # ----------------------------------------------------------

    def test_text_attachment_returns_text_block(self):
        att = self._make_attachment(
            'notes.txt',
            'text/plain',
            b'hello world',
        )
        block = self._call(self._attachment_uri(att))
        self.assertEqual(block['type'], 'text')
        self.assertEqual(block['text'], 'hello world')

    def test_json_attachment_returns_text_block(self):
        att = self._make_attachment(
            'config.json',
            'application/json',
            b'{"k": "v"}',
        )
        block = self._call(self._attachment_uri(att))
        self.assertEqual(block['type'], 'text')

    def test_svg_attachment_returns_text_block(self):
        svg = b'<svg xmlns="http://www.w3.org/2000/svg"/>'
        att = self._make_attachment('icon.svg', 'image/svg+xml', svg)
        block = self._call(self._attachment_uri(att))
        self.assertEqual(block['type'], 'text')
        self.assertEqual(block['text'], svg.decode('utf-8'))

    def test_image_attachment_returns_image_block(self):
        raw = bytes(range(64))
        att = self._make_attachment('pic.png', 'image/png', raw)
        block = self._call(self._attachment_uri(att))
        self.assertEqual(block['type'], 'image')
        self.assertEqual(block['mimeType'], 'image/png')
        self.assertEqual(base64.b64decode(block['data']), raw)

    def test_audio_attachment_returns_audio_block(self):
        raw = bytes(range(32))
        att = self._make_attachment('clip.wav', 'audio/wav', raw)
        block = self._call(self._attachment_uri(att))
        self.assertEqual(block['type'], 'audio')
        self.assertEqual(block['mimeType'], 'audio/wav')

    def test_binary_attachment_returns_resource_block_with_name(self):
        raw = b'\x00' * 64
        att = self._make_attachment('blob.bin', 'application/octet-stream', raw)
        block = self._call(self._attachment_uri(att))
        self.assertEqual(block['type'], 'resource')
        resource = block['resource']
        self.assertEqual(resource['mimeType'], 'application/octet-stream')
        self.assertEqual(resource['uri'], self._attachment_uri(att))
        self.assertEqual(resource['name'], 'blob.bin')
        self.assertEqual(base64.b64decode(resource['blob']), raw)

    def test_pdf_attachment_unparseable_returns_resource_only(self):
        raw = b'%PDF-1.4\n%not-really-a-pdf'
        att = self._make_attachment('doc.pdf', 'application/pdf', raw)
        block = self._call(self._attachment_uri(att))
        self.assertEqual(block['type'], 'resource')
        self.assertEqual(block['resource']['mimeType'], 'application/pdf')
        self.assertEqual(block['resource']['name'], 'doc.pdf')

    def test_pdf_attachment_auto_returns_text_and_resource(self):
        raw = self._build_pdf('Hello PDF World')
        att = self._make_attachment('greet.pdf', 'application/pdf', raw)
        blocks = self._call_raw(self._attachment_uri(att))
        self.assertEqual(len(blocks), 2)
        self.assertEqual(blocks[0]['type'], 'text')
        self.assertIn('Hello PDF World', blocks[0]['text'])
        self.assertEqual(blocks[1]['type'], 'resource')
        self.assertEqual(
            blocks[1]['resource']['mimeType'],
            'application/pdf',
        )
        self.assertEqual(blocks[1]['resource']['name'], 'greet.pdf')
        self.assertEqual(
            base64.b64decode(blocks[1]['resource']['blob']),
            raw,
        )

    def test_pdf_attachment_format_resource_returns_resource_only(self):
        raw = self._build_pdf('Hello PDF World')
        att = self._make_attachment('greet.pdf', 'application/pdf', raw)
        blocks = self._call_raw(
            self._attachment_uri(att),
            format='resource',
        )
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0]['type'], 'resource')
        self.assertEqual(
            blocks[0]['resource']['mimeType'],
            'application/pdf',
        )

    def test_pdf_attachment_format_text_returns_text_only(self):
        raw = self._build_pdf('Hello PDF World')
        att = self._make_attachment('greet.pdf', 'application/pdf', raw)
        blocks = self._call_raw(
            self._attachment_uri(att),
            format='text',
        )
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0]['type'], 'text')
        self.assertIn('Hello PDF World', blocks[0]['text'])

    def test_pdf_attachment_format_text_unparseable_raises(self):
        raw = b'%PDF-1.4\n%not-really-a-pdf'
        att = self._make_attachment('doc.pdf', 'application/pdf', raw)
        with self.assertRaises(UserError):
            self._call_raw(self._attachment_uri(att), format='text')

    def test_unknown_format_raises(self):
        att = self._make_attachment(
            'notes.txt',
            'text/plain',
            b'hello',
        )
        with self.assertRaises(UserError):
            self._call_raw(self._attachment_uri(att), format='bogus')

    def test_format_ignored_for_non_pdf(self):
        att = self._make_attachment(
            'notes.txt',
            'text/plain',
            b'hello',
        )
        blocks = self._call_raw(
            self._attachment_uri(att),
            format='resource',
        )
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0]['type'], 'text')
        self.assertEqual(blocks[0]['text'], 'hello')

    def test_xlsx_attachment_auto_returns_text_and_resource(self):
        raw = self._build_xlsx('Hello XLSX World')
        att = self._make_attachment(
            'sheet.xlsx',
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            raw,
        )
        blocks = self._call_raw(self._attachment_uri(att))
        self.assertEqual(len(blocks), 2)
        self.assertEqual(blocks[0]['type'], 'text')
        self.assertIn('Hello XLSX World', blocks[0]['text'])
        self.assertEqual(blocks[1]['type'], 'resource')
        self.assertEqual(blocks[1]['resource']['name'], 'sheet.xlsx')

    def test_text_with_invalid_utf8_falls_back_to_resource(self):
        att = self._make_attachment(
            'broken.txt',
            'text/plain',
            b'\xff\xfe\x00bad',
        )
        block = self._call(self._attachment_uri(att))
        self.assertEqual(block['type'], 'resource')
        self.assertEqual(block['resource']['mimeType'], 'text/plain')

    def test_mimetype_with_charset_is_normalized(self):
        att = self._make_attachment(
            'notes.txt',
            'text/plain; charset=utf-8',
            b'hi',
        )
        block = self._call(self._attachment_uri(att))
        self.assertEqual(block['type'], 'text')
        self.assertEqual(block['text'], 'hi')

    def test_unknown_attachment_raises(self):
        with self.assertRaises(UserError):
            self._call('odoo://attachment/999999999')

    def test_invalid_uri_scheme_raises(self):
        with self.assertRaises(UserError):
            self._call('http://example.com/file.png')

    def test_garbage_uri_raises(self):
        with self.assertRaises(UserError):
            self._call('not a uri')

    # ----------------------------------------------------------
    # Tests — record-field uri
    # ----------------------------------------------------------

    def test_record_field_image_returns_image_block(self):
        raw_b64 = (
            b'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQ'
            b'VQYV2NgAAIAAAUAAarVyFEAAAAASUVORK5CYII='
        )
        partner = self.env['res.partner'].create(
            {
                'name': 'Imgr',
                'image_1920': raw_b64,
            },
        )
        block = self._call(
            'odoo://record/res.partner/%d/image_1920' % partner.id,
        )
        self.assertEqual(block['type'], 'image')
        self.assertTrue(block['mimeType'].startswith('image/'))

    def test_record_field_unknown_field_raises(self):
        with self.assertRaises(UserError):
            self._call(
                'odoo://record/res.partner/%d/no_such_field' % self.partner.id,
            )

    def test_record_field_non_binary_raises(self):
        with self.assertRaises(UserError):
            self._call(
                'odoo://record/res.partner/%d/name' % self.partner.id,
            )

    def test_record_field_unknown_record_raises(self):
        with self.assertRaises(UserError):
            self._call('odoo://record/res.partner/999999999/image_1920')

    def test_record_field_unknown_model_raises(self):
        with self.assertRaises(UserError):
            self._call('odoo://record/no.such.model/1/x')

    def test_record_field_enforces_field_groups(self):
        self.patch(
            self.env['res.partner']._fields['image_1920'],
            'groups',
            'base.group_system',
        )
        self.acl_partner.with_user(self.acl_user).check_access('read')
        mixin = self.mixin.with_user(self.acl_user)
        with self.assertRaises(AccessError):
            mixin._resolve_resource_record_field(
                'res.partner',
                self.acl_partner.id,
                'image_1920',
            )

    def test_record_field_allows_ungrouped_field(self):
        mixin = self.mixin.with_user(self.acl_user)
        mimetype, raw, _name = mixin._resolve_resource_record_field(
            'res.partner',
            self.acl_partner.id,
            'image_1920',
        )
        self.assertTrue(mimetype.startswith('image/'))
        self.assertTrue(raw)
