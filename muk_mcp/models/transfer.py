import hashlib
import secrets
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.http import request

from odoo.addons.muk_mcp.tools.uri import attachment_uri

TRANSFER_PATH = '/mcp/transfer'
TRANSFER_MINUTES = 15
TRANSFER_TTL = timedelta(minutes=TRANSFER_MINUTES)
STAGED_RETENTION = timedelta(days=1)


class MCPTransfer(models.Model):

    _name = 'muk_mcp.transfer'
    _description = "MCP File Transfer"
    _order = 'id desc'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    token_hash = fields.Char(
        string="Token Hash",
        required=True,
        index=True,
        copy=False,
    )

    operation = fields.Selection(
        selection=[
            ('upload', "Upload"),
            ('download', "Download"),
        ],
        string="Operation",
        required=True,
    )

    key_name = fields.Char(
        string="Key",
        help="The API key the link was issued to.",
    )

    user_id = fields.Many2one(
        comodel_name='res.users',
        string="User",
        required=True,
        index=True,
        ondelete='cascade',
    )

    attachment_id = fields.Many2one(
        comodel_name='ir.attachment',
        string="Attachment",
        help="The attachment an upload fills.",
        ondelete='set null',
    )

    uri = fields.Char(
        string="URI",
        help="The odoo:// resource a download serves.",
    )

    file_size = fields.Integer(
        string="Announced Size",
    )

    sha256 = fields.Char(
        string="Announced SHA-256",
    )

    expires_at = fields.Datetime(
        string="Expires At",
        required=True,
    )

    used = fields.Boolean(
        string="Used",
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _receive(self, data):
        """Fill the upload's attachment with ``data``, as the link's user.

        :raise UserError: when the data is empty or does not match the announced
            size or digest.
        """
        self.ensure_one()
        if not data:
            raise UserError(_(
                "The upload is empty: send the file as the raw request body "
                "(curl -T) or as a multipart file."
            ))
        digest = hashlib.sha256(data).hexdigest()
        if self.file_size and len(data) != self.file_size:
            raise UserError(_(
                "The upload has %(got)s bytes, %(want)s were announced.",
                got=len(data),
                want=self.file_size,
            ))
        if self.sha256 and digest != self.sha256.lower():
            raise UserError(_("The upload does not match the announced SHA-256."))
        attachment = self.attachment_id.with_user(self.user_id)
        attachment.write({'raw': data})
        return {
            'file': attachment_uri(attachment.id),
            'file_size': len(data),
            'sha256': digest,
        }

    def _download(self):
        """Stream the download's resource, read as the link's user."""
        self.ensure_one()
        env = self.env(user=self.user_id)
        record, field = env['muk_mcp.mixin']._resolve_resource_target(self.uri)
        return env['ir.binary']._get_stream_from(record, field).get_response(
            as_attachment=True,
        )

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    def _issue(self, operation, **values):
        """Create a link for the current user and return it with its URL."""
        token = secrets.token_urlsafe(32)
        key = getattr(request, '_mcp_key', None) if request else None
        transfer = self.sudo().create({
            **values,
            'operation': operation,
            'token_hash': self.env['muk_mcp.key']._hash_key(token),
            'user_id': self.env.uid,
            'key_name': key.name if key else False,
            'expires_at': fields.Datetime.now() + TRANSFER_TTL,
        })
        return transfer, f'{self.get_base_url()}{TRANSFER_PATH}/{token}'

    @api.model
    def _redeem(self, token, operation):
        """Consume the live, unused link behind ``token``, or return an empty set."""
        transfer = self.sudo().search(
            [
                ('token_hash', '=', self.env['muk_mcp.key']._hash_key(token)),
                ('operation', '=', operation),
                ('used', '=', False),
                ('expires_at', '>', fields.Datetime.now()),
                ('user_id.active', '=', True),
            ],
            limit=1,
        )
        transfer.used = True
        return transfer

    # ----------------------------------------------------------
    # Cron
    # ----------------------------------------------------------

    @api.autovacuum
    def _autovacuum_transfers(self):
        """Drop staged upload files a day past expiry, links with the audit log."""
        transfers = self.sudo()
        transfers.search([
            ('expires_at', '<', fields.Datetime.now() - STAGED_RETENTION),
            ('attachment_id.res_model', '=', False),
        ]).attachment_id.unlink()
        limit = self.env['muk_mcp.log']._retention_limit()
        transfers.search([('create_date', '<', limit)]).unlink()
