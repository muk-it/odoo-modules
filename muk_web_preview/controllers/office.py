from __future__ import annotations

from odoo import http
from odoo.http import Response, request

from odoo.addons.muk_web_preview.tools.office import (
    sign_attachment,
    verify_attachment,
    viewer_url,
)


class OfficeController(http.Controller):
    """Hand Office files to the Office Online viewer through signed links."""

    # ----------------------------------------------------------
    # Routes
    # ----------------------------------------------------------

    @http.route(
        '/web_preview/office/<int:attachment_id>',
        type='jsonrpc',
        auth='user',
        readonly=True,
    )
    def office_viewer_url(self, attachment_id: int) -> str:
        """Return the Office Online viewer URL for a readable attachment."""
        if (
            not request.env['ir.config_parameter']
            .sudo()
            .get_bool('muk_web_preview.office_enabled')
        ):
            raise request.not_found()
        attachment = request.env['ir.attachment'].browse(attachment_id)
        attachment.check_access('read')
        token = sign_attachment(request.env, attachment.id)
        return viewer_url(
            f'{attachment.get_base_url()}/web_preview/office/file/{token}'
        )

    @http.route(
        '/web_preview/office/file/<string:token>',
        type='http',
        auth='public',
        readonly=True,
    )
    def office_file(self, token: str) -> Response:
        """Stream the attachment of a valid, unexpired token."""
        attachment_id = verify_attachment(request.env, token)
        attachment = request.env['ir.attachment'].sudo().browse(attachment_id).exists()
        if not attachment_id or not attachment:
            raise request.not_found()
        return request.env['ir.binary']._get_stream_from(attachment).get_response()
