# Copyright 2026, Jarsa
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl.html).

import contextlib

from odoo import api, fields, models
from odoo.http import request


class MCPKey(models.Model):
    _inherit = "muk_mcp.key"

    @api.model
    def authenticate(self, token):
        """OAuth access tokens are materialized as MCP keys; reject the key
        when its OAuth token is expired or revoked (60-minute TTL instead of
        the standing key policy)."""
        key = super().authenticate(token)
        if not key:
            return None
        oauth_token = self.env["muk_mcp.oauth.token"].sudo().search([("mcp_key_id", "=", key.id)], limit=1)
        if not oauth_token:
            return key
        now = fields.Datetime.now()
        if oauth_token.revoked or oauth_token.access_expiration < now:
            return None
        with contextlib.suppress(Exception), self.env.cr.savepoint():
            oauth_token.write(
                {
                    "last_used": now,
                    "last_ip": request.httprequest.remote_addr if request else False,
                }
            )
        return key
