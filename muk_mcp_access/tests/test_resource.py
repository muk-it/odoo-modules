from __future__ import annotations

from unittest.mock import patch

from odoo import models
from odoo.exceptions import AccessError
from odoo.tests import common, tagged


@tagged('post_install', '-at_install')
class TestMCPAccessResource(common.TransactionCase):
    """Cover the allowlist enforcement on the ``read_resource`` attachment URI."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.access_model = cls.env['muk_mcp_access.model']
        cls.mixin = cls.env['muk_mcp.mixin']

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _allow(self, model_name: str, *, domain: str = '') -> None:
        """Add a read-only allowlist entry for a model."""
        self.access_model.create(
            {
                'model_id': self.env['ir.model']._get_id(model_name),
                'allow_read': True,
                'allow_write': False,
                'domain': domain,
            }
        )

    def _attach(
        self,
        model_name: str,
        record_id: int,
        payload: bytes,
    ) -> models.BaseModel:
        """Create a textual attachment linked to a record."""
        return self.env['ir.attachment'].create(
            {
                'name': 'resource.txt',
                'raw': payload,
                'mimetype': 'text/plain',
                'res_model': model_name,
                'res_id': record_id,
            }
        )

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_attachment_of_unlisted_model_is_denied(self):
        self._allow('res.partner')
        attachment = self._attach(
            'res.country',
            self.env.ref('base.be').id,
            b'top secret',
        )
        with self.assertRaises(AccessError):
            self.mixin._mcp_read_resource('odoo://attachment/%d' % attachment.id)

    def test_attachment_of_listed_model_is_returned(self):
        self._allow('res.partner')
        partner = self.env['res.partner'].create({'name': 'Resource Owner'})
        attachment = self._attach(
            'res.partner',
            partner.id,
            b'fine',
        )
        content = self.mixin._mcp_read_resource('odoo://attachment/%d' % attachment.id)
        self.assertEqual(content[0]['text'], 'fine')

    def test_attachment_outside_the_record_domain_is_denied(self):
        self._allow('res.country', domain="[('code', '=', 'BE')]")
        attachment = self._attach(
            'res.country',
            self.env.ref('base.fr').id,
            b'out of domain',
        )
        with self.assertRaises(AccessError):
            self.mixin._mcp_read_resource('odoo://attachment/%d' % attachment.id)

    def test_attachment_on_an_exempt_model_is_returned(self):
        self._allow('res.partner')
        attachment = self._attach(
            'res.country',
            self.env.ref('base.be').id,
            b'payload',
        )
        with patch.object(
            type(self.mixin),
            '_mcp_attachment_exempt_models',
            lambda _self: frozenset({'res.country'}),
        ):
            content = self.mixin._mcp_read_resource(
                'odoo://attachment/%d' % attachment.id
            )
        self.assertEqual(content[0]['text'], 'payload')

    def test_unlinked_attachment_is_returned(self):
        self._allow('res.partner')
        attachment = self.env['ir.attachment'].create(
            {
                'name': 'loose.txt',
                'raw': b'loose',
                'mimetype': 'text/plain',
            }
        )
        content = self.mixin._mcp_read_resource('odoo://attachment/%d' % attachment.id)
        self.assertEqual(content[0]['text'], 'loose')
