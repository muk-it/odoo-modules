import json

from werkzeug.exceptions import NotFound

from odoo import http
from odoo.exceptions import AccessError, UserError
from odoo.http import Response, request

from odoo.addons.muk_mcp.models.transfer import TRANSFER_PATH


class MCPTransferController(http.Controller):

    @http.route(
        f'{TRANSFER_PATH}/<string:token>',
        type='http',
        auth='public',
        methods=['GET', 'PUT'],
        csrf=False,
        save_session=False,
    )
    def transfer(self, token, **kw):
        """Stream a download on GET, take the request body or its file on PUT.

        :raise werkzeug.exceptions.NotFound: when the link is unknown, used or expired.
        """
        operation = 'download' if request.httprequest.method == 'GET' else 'upload'
        files = request.httprequest.files
        data = next(files.values()).read() if files else request.httprequest.get_data()
        if not (link := request.env['muk_mcp.transfer']._redeem(token, operation)):
            raise NotFound()
        try:
            if operation == 'download':
                return link._download()
            result, status = link._receive(data), 200
        except UserError as exc:
            result = {'error': str(exc)}
            status = 403 if isinstance(exc, AccessError) else 400
        return Response(
            json.dumps(result),
            status=status,
            headers={'Content-Type': 'application/json'},
        )
