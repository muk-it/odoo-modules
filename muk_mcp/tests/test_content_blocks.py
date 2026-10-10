from odoo.tests import common

from odoo.addons.muk_mcp.tools import content


class TestContentBlocks(common.TransactionCase):
    """Cover mimetype normalization and content-block selection for raw bytes."""

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_normalize_mimetype_strips_whitespace_and_parameters(self):
        self.assertEqual(
            content.normalize_mimetype('  Text/Plain ; charset=utf-8; boundary=x  '),
            'text/plain',
        )

    def test_normalize_mimetype_keeps_only_the_first_parameter_split(self):
        self.assertEqual(
            content.normalize_mimetype('application/json;a=1;b=2'),
            'application/json',
        )

    def test_textual_application_mimetypes(self):
        for mimetype in (
            'application/json',
            'application/xml',
            'application/yaml',
            'application/x-yaml',
            'application/javascript',
            'application/ecmascript',
            'application/x-sh',
            'application/x-python',
            'image/svg+xml',
        ):
            self.assertTrue(content.is_textual_mimetype(mimetype), mimetype)

    def test_non_textual_mimetypes(self):
        for mimetype in ('application/pdf', 'application/zip', 'image/png', ''):
            self.assertFalse(content.is_textual_mimetype(mimetype), mimetype)

    def test_resource_block_carries_name(self):
        block = content.make_content_for_bytes(
            'odoo://attachment/1',
            'application/pdf',
            raw_bytes=b'%PDF-',
            name='invoice.pdf',
        )
        self.assertEqual(block['resource']['name'], 'invoice.pdf')
        self.assertEqual(block['resource']['mimeType'], 'application/pdf')
