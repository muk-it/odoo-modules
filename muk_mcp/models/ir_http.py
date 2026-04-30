import re

import werkzeug

from odoo import api, models, SUPERUSER_ID
from odoo.tools.misc import str2bool
from odoo.http import request


class IrHttp(models.AbstractModel):

    _inherit = 'ir.http'

    @classmethod
    def _auth_method_mcp(cls):
        env = api.Environment(request.cr, SUPERUSER_ID, {})
        header = request.httprequest.headers.get('Authorization', '')
        match = re.match(r'^bearer\s+(.+)$', header, re.IGNORECASE)
        if not (token := match and match.group(1).strip()):
            raise werkzeug.exceptions.Unauthorized()
        if not (mcp_key := env['muk_mcp.key'].authenticate(token)):
            raise werkzeug.exceptions.Unauthorized()
        request.uid = mcp_key.user_id.id
        request._mcp_key = mcp_key
        annotate = env['ir.config_parameter'].get_param(
            'muk_mcp.annotate_messages', 'True',
        )
        if str2bool(annotate, default=True):
            ctx = dict(request.context)
            ctx['mcp_name'] = mcp_key.name
            request.context = ctx
