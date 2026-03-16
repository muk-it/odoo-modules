import re

import werkzeug

from odoo import models
from odoo.http import request


class IrHttp(models.AbstractModel):

    _inherit = 'ir.http'

    # ----------------------------------------------------------
    # Authentication
    # ----------------------------------------------------------

    @classmethod
    def _auth_method_mcp(cls):
        header = request.httprequest.headers.get('Authorization', '')
        match = re.match(r'^bearer\s+(.+)$', header, re.IGNORECASE)
        token = match and match.group(1).strip()
        if not token:
            raise werkzeug.exceptions.Unauthorized()
        mcp_key = request.env['muk_mcp.key'].authenticate(token)
        if not mcp_key:
            raise werkzeug.exceptions.Unauthorized()
        request._mcp_key = mcp_key
        request.update_env(user=mcp_key.user_id.id)
        request.session.can_save = False
