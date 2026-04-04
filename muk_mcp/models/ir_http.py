import re

import werkzeug

from odoo import api, models, SUPERUSER_ID
from odoo.http import request
from odoo.tools.misc import str2bool


class IrHttp(models.AbstractModel):

    _inherit = 'ir.http'

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @classmethod
    def _auth_method_mcp(cls):
        env = api.Environment(request.env.cr, SUPERUSER_ID, {})
        header = request.httprequest.headers.get('Authorization', '')
        match = re.match(r'^bearer\s+(.+)$', header, re.IGNORECASE)
        token = match and match.group(1).strip()
        if not token:
            raise werkzeug.exceptions.Unauthorized()
        mcp_key = env['muk_mcp.key'].authenticate(token)
        if not mcp_key:
            raise werkzeug.exceptions.Unauthorized()
        request._mcp_key = mcp_key
        request.update_env(user=mcp_key.user_id.id)
        if str2bool(env['ir.config_parameter'].get_param(
            'muk_mcp.annotate_messages', 'True',
        ), default=True):
            request.update_env(context={
                'mcp_via': True,
                'mcp_key_name': mcp_key.name,
            })
        request.session.can_save = False

    @classmethod
    def _handle_error(cls, exception):
        if (
            getattr(request, 'dispatcher', None) and 
            request.dispatcher.routing_type == 'mcp'
        ):
            if isinstance(exception, werkzeug.exceptions.HTTPException):
                return request.make_json_response({
                    'jsonrpc': '2.0',
                    'id': None,
                    'error': {
                        'code': -32603,
                        'message': str(exception),
                    },
                }, status=exception.code)
        return super()._handle_error(exception)
