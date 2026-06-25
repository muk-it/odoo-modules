from __future__ import annotations

import hashlib
import hmac
import secrets
import time

from odoo import http
from odoo.http import request


class OfficePreviewController(http.Controller):
    """Serve Office documents through the Office Online viewer via signed tokens."""

    # ----------------------------------------------------------
    # Properties
    # ----------------------------------------------------------

    @property
    def _token_ttl(self) -> int:
        return 300

    @property
    def _viewer_url(self) -> str:
        return 'https://view.officeapps.live.com/op/embed.aspx'

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _get_secret(self) -> str:
        """Return the database secret used to sign file access tokens."""
        return request.env['ir.config_parameter'].sudo().get_param('database.secret')

    def _generate_token(self, attachment_id: int) -> str:
        """Build a signed, time-limited access token for an attachment."""
        secret = self._get_secret()
        nonce = secrets.token_hex(16)
        expires = int(time.time()) + self._token_ttl
        payload = f'{attachment_id}:{expires}:{nonce}'
        signature = hmac.new(
            secret.encode(),
            payload.encode(),
            hashlib.sha256,
        ).hexdigest()
        return f'{payload}:{signature}'

    def _verify_token(self, token: str, attachment_id: int) -> bool:
        """Validate a file access token against its attachment and expiry."""
        parts = token.split(':')
        if len(parts) != 4:
            return False
        token_id, expires_str, nonce, signature = parts
        try:
            if int(token_id) != attachment_id:
                return False
            if int(expires_str) < int(time.time()):
                return False
        except (ValueError, TypeError):
            return False
        secret = self._get_secret()
        payload = f'{token_id}:{expires_str}:{nonce}'
        expected = hmac.new(
            secret.encode(),
            payload.encode(),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(signature, expected)

    # ----------------------------------------------------------
    # Routes
    # ----------------------------------------------------------

    @http.route(
        '/muk_web_preview/office/token',
        auth='user',
        type='jsonrpc',
    )
    def generate_office_token(self, attachment_id) -> dict:
        """Return the Office Online viewer URL for a readable attachment."""
        enabled = (
            request.env['ir.config_parameter']
            .sudo()
            .get_param('muk_web_preview.office_enabled', 'False')
        )
        if enabled not in ('True', 'true', '1'):
            return {'error': 'Office preview is disabled'}
        attachment = request.env['ir.attachment'].browse(int(attachment_id))
        attachment.check_access('read')
        token = self._generate_token(attachment.id)
        base_url = request.env['ir.config_parameter'].sudo().get_param('web.base.url')
        file_url = (
            f'{base_url}/muk_web_preview/office/file/{attachment.id}?token={token}'
        )
        return {
            'viewer_url': f'{self._viewer_url}?src={file_url}',
        }

    @http.route(
        '/muk_web_preview/office/file/<int:id>',
        auth='public',
        type='http',
        csrf=False,
    )
    def serve_office_file(self, id, token: str | None = None, **kw):
        """Stream the attachment file when its access token is valid."""
        if not token or not self._verify_token(token, id):
            return request.not_found()
        attachment = request.env['ir.attachment'].sudo().browse(id)
        if not attachment.exists():
            return request.not_found()
        stream = (
            request.env['ir.binary']
            .sudo()
            ._get_stream_from(
                attachment,
                'raw',
                attachment.name,
                'name',
                attachment.mimetype,
            )
        )
        return stream.get_response()
