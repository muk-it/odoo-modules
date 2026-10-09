import base64
import hashlib
import json
from datetime import timedelta
from urllib.parse import urlparse

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.muk_mcp.tests.common import MCPHttpCase

PDF = b'%PDF-1.4 MCP transfer test'
PNG = (
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQ'
    'VQYV2NgAAIAAAUAAarVyFEAAAAASUVORK5CYII='
)


@tagged('post_install', '-at_install')
class TestMcpTransfer(MCPHttpCase):
    """Cover the one-time upload and download links and the files they carry."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.mcp_user.groups_id += cls.env.ref('base.group_partner_manager')
        cls.partner = cls.env['res.partner'].create(
            {'name': 'MCP Transfer Partner', 'image_1920': PNG}
        )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def call(self, name, arguments):
        """Run tool ``name`` as the MCP user and decode its result."""
        env = self.env(user=self.mcp_user)
        text, _info = env['muk_mcp.tool']._call(name, arguments, env)
        return json.loads(text)

    def send(self, url, data=None, **kwargs):
        """GET the link at ``url``, or PUT ``data`` to it, through the test server."""
        url = self.base_url() + urlparse(url).path
        if data is None and not kwargs:
            return self.opener.get(url, timeout=12)
        return self.opener.put(url, data=data, timeout=12, **kwargs)

    def link(self, name='offer.pdf', **arguments):
        """Authorize an upload, with ``arguments`` added to the call."""
        return self.call('authorize_upload', {'name': name, **arguments})

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_an_upload_link_takes_the_file_once_and_upload_file_files_it(self):
        for body in ({'data': PDF}, {'files': {'file': ('offer.pdf', PDF)}}):
            with self.subTest(body=list(body)):
                link = self.link(size=len(PDF), sha256=hashlib.sha256(PDF).hexdigest())
                self.assertEqual(self.send(link['upload_url']).status_code, 404)
                self.assertEqual(
                    self.send(link['upload_url'], **body).json()['file'], link['file']
                )
                self.assertEqual(self.send(link['upload_url'], PDF).status_code, 404)
                result = self.call('upload_file', {
                    'file': link['file'],
                    'model': 'res.partner',
                    'id': self.partner.id,
                })
                attachment = self.env['ir.attachment'].browse(result['id'])
                self.assertEqual(
                    (attachment.raw, attachment.name, attachment.res_id),
                    (PDF, 'offer.pdf', self.partner.id),
                )

    def test_a_download_link_streams_attachments_and_fields_once(self):
        attachment = self.env['ir.attachment'].with_user(self.mcp_user).create(
            {'name': 'note.txt', 'raw': b'hello'}
        )
        for uri, content in (
            (f'odoo://attachment/{attachment.id}', b'hello'),
            (
                f'odoo://record/res.partner/{self.partner.id}/image_1920',
                base64.b64decode(self.partner.image_1920),
            ),
        ):
            with self.subTest(uri=uri):
                link = self.call('authorize_download', {'uri': uri})
                self.assertEqual(self.send(link['download_url']).content, content)
                self.assertEqual(self.send(link['download_url']).status_code, 404)

    def test_a_produced_file_is_linked_only_for_clients_over_http(self):
        self.mcp_user.groups_id += self.env.ref('base.group_allow_export')
        arguments = {
            'model': 'res.partner',
            'fields': ['name'],
            'ids': [self.partner.id],
            'delivery': 'link',
        }
        inline = self.call('export_records', arguments)
        response = self.mcp_stateless_post(
            'tools/call', {'name': 'export_records', 'arguments': arguments}
        )
        linked = json.loads(response.json()['result']['content'][0]['text'])
        self.assertNotIn('content_base64', linked)
        self.assertEqual(
            self.send(linked['download_url']).content,
            base64.b64decode(inline['content_base64']),
        )

    def test_an_upload_that_breaks_its_announcement_or_expired_is_refused(self):
        for announced, status in (
            ({'size': len(PDF) + 1}, 400),
            ({'sha256': hashlib.sha256(b'other').hexdigest()}, 400),
            ({}, 404),
        ):
            with self.subTest(announced=announced):
                link = self.link(**announced)
                if not announced:
                    self.env['muk_mcp.transfer'].search([], limit=1).expires_at = (
                        fields.Datetime.now() - timedelta(minutes=1)
                    )
                self.assertEqual(self.send(link['upload_url'], PDF).status_code, status)
                with self.assertRaisesRegex(UserError, 'is empty'):
                    self.call('upload_file', {'file': link['file']})

    def test_a_link_dies_with_its_file_or_its_user(self):
        file = self.env['ir.attachment'].with_user(self.mcp_user).create(
            {'name': 'gone.txt', 'raw': b'x'}
        )
        link = self.call('authorize_download', {'uri': f'odoo://attachment/{file.id}'})
        file.unlink()
        self.assertEqual(self.send(link['download_url']).status_code, 400)
        link = self.link()
        self.mcp_user.active = False
        self.assertEqual(self.send(link['upload_url'], PDF).status_code, 404)

    def test_staged_files_are_vacuumed_first_and_links_with_the_audit_log(self):
        self.link()
        transfer = self.env['muk_mcp.transfer'].search([], limit=1)
        staged = transfer.attachment_id
        transfer.expires_at = fields.Datetime.now() - timedelta(days=2)
        self.env['muk_mcp.transfer']._autovacuum_transfers()
        self.assertFalse(staged.exists())
        self.assertTrue(transfer.exists())
        self.env.cr.execute(
            'UPDATE muk_mcp_transfer SET create_date = %s WHERE id = %s',
            (fields.Datetime.now() - timedelta(days=400), transfer.id),
        )
        transfer.invalidate_recordset()
        self.env['muk_mcp.transfer']._autovacuum_transfers()
        self.assertFalse(transfer.exists())
