from odoo.exceptions import AccessError
from odoo.tests import common
from odoo.tests.common import new_test_user

PNG = (
    b'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQ'
    b'VQYV2NgAAIAAAUAAarVyFEAAAAASUVORK5CYII='
)


class TestReadResource(common.TransactionCase):
    """Cover the access checks behind every tool that reads a file."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.acl_partner = cls.env['res.partner'].create({
            'name': 'Confidential Owner',
            'image_1920': PNG,
        })
        cls.acl_user = new_test_user(
            cls.env, login='mcp_field_acl_user', groups='base.group_user',
        )

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_untyped_attachment_takes_the_type_of_its_name(self):
        raw = b'Read me.'
        attachment = self.env['ir.attachment'].create({
            'name': 'notes.txt',
            'mimetype': 'application/octet-stream',
            'raw': raw,
        })
        mimetype, content, name = self.env['muk_mcp.mixin']._resolve_resource_uri(
            'odoo://attachment/%d' % attachment.id,
        )
        self.assertEqual((mimetype, content, name), ('text/plain', raw, 'notes.txt'))

    def test_record_field_enforces_field_groups(self):
        self.patch(
            self.env['res.partner']._fields['image_1920'],
            'groups',
            'base.group_system',
        )
        mixin = self.env['muk_mcp.mixin'].with_user(self.acl_user)
        uri = 'odoo://record/res.partner/%d/image_1920' % self.acl_partner.id
        _mimetype, raw, _name = mixin._resolve_resource_uri(
            uri.replace('image_1920', 'image_128'),
        )
        self.assertTrue(raw)
        for resolve in (mixin._resolve_resource_uri, mixin._mcp_authorize_download):
            with self.subTest(resolve=resolve.__name__):
                with self.assertRaises(AccessError):
                    resolve(uri)
