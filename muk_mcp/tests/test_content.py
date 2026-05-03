import base64

from odoo.tests import common

from odoo.addons.muk_mcp.tools import content


class TestContent(common.TransactionCase):

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_normalize_mimetype_strips_charset(self):
        self.assertEqual(
            content.normalize_mimetype('text/plain; charset=utf-8'),
            'text/plain',
        )

    def test_normalize_mimetype_lowercases(self):
        self.assertEqual(
            content.normalize_mimetype('IMAGE/PNG'), 'image/png',
        )

    def test_normalize_mimetype_empty(self):
        self.assertEqual(content.normalize_mimetype(None), '')
        self.assertEqual(content.normalize_mimetype(''), '')

    def test_is_textual_mimetype(self):
        self.assertTrue(content.is_textual_mimetype('text/plain'))
        self.assertTrue(content.is_textual_mimetype('text/csv'))
        self.assertTrue(content.is_textual_mimetype('application/json'))
        self.assertTrue(content.is_textual_mimetype('image/svg+xml'))
        self.assertFalse(content.is_textual_mimetype('image/png'))
        self.assertFalse(content.is_textual_mimetype('application/pdf'))
        self.assertFalse(content.is_textual_mimetype(''))

    def test_make_content_text_from_raw_bytes(self):
        block = content.make_content_for_bytes(
            'odoo://test/1', 'text/plain', raw_bytes=b'hello',
        )
        self.assertEqual(block['type'], 'text')
        self.assertEqual(block['text'], 'hello')

    def test_make_content_text_from_base64(self):
        block = content.make_content_for_bytes(
            'odoo://test/1', 'application/json',
            base64_str=base64.b64encode(b'{"k":1}').decode(),
        )
        self.assertEqual(block['type'], 'text')
        self.assertEqual(block['text'], '{"k":1}')

    def test_make_content_image(self):
        raw = bytes(range(32))
        block = content.make_content_for_bytes(
            'odoo://test/1', 'image/png', raw_bytes=raw,
        )
        self.assertEqual(block['type'], 'image')
        self.assertEqual(block['mimeType'], 'image/png')
        self.assertEqual(base64.b64decode(block['data']), raw)

    def test_make_content_audio(self):
        raw = bytes(range(16))
        block = content.make_content_for_bytes(
            'odoo://test/1', 'audio/wav', raw_bytes=raw,
        )
        self.assertEqual(block['type'], 'audio')
        self.assertEqual(block['mimeType'], 'audio/wav')
        self.assertEqual(base64.b64decode(block['data']), raw)

    def test_make_content_resource_for_pdf(self):
        raw = b'%PDF-1.4\n%not-really'
        block = content.make_content_for_bytes(
            'odoo://test/1', 'application/pdf', raw_bytes=raw,
        )
        self.assertEqual(block['type'], 'resource')
        self.assertEqual(block['resource']['uri'], 'odoo://test/1')
        self.assertEqual(block['resource']['mimeType'], 'application/pdf')
        self.assertEqual(base64.b64decode(block['resource']['blob']), raw)

    def test_make_content_resource_for_unknown_mime(self):
        block = content.make_content_for_bytes(
            'odoo://test/1', '', raw_bytes=b'\x00\x01',
        )
        self.assertEqual(block['type'], 'resource')
        self.assertNotIn('mimeType', block['resource'])

    def test_text_with_invalid_utf8_falls_back_to_resource(self):
        block = content.make_content_for_bytes(
            'odoo://test/1', 'text/plain',
            raw_bytes=b'\xff\xfe\x00bad',
        )
        self.assertEqual(block['type'], 'resource')
        self.assertEqual(block['resource']['mimeType'], 'text/plain')

    def test_raises_when_neither_input_provided(self):
        with self.assertRaises(ValueError):
            content.make_content_for_bytes('odoo://test/1', 'text/plain')

    def test_passes_b64_through_without_reencoding_for_binary(self):
        raw = bytes(range(32))
        original_b64 = base64.b64encode(raw).decode()
        block = content.make_content_for_bytes(
            'odoo://test/1', 'image/png', base64_str=original_b64,
        )
        self.assertEqual(block['data'], original_b64)
