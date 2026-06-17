from odoo import api, models
from odoo.http import request

from odoo.addons.muk_mcp.core.tool import get_tool_index


class MCPTool(models.Model):

    _inherit = 'muk_mcp.tool'

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _call(self, name, arguments, env, enforce_scope=None):
        entry = get_tool_index(env).get(name)
        if entry and request:
            request._mcp_tool_category = entry.get('category', 'read')
        try:
            return super()._call(name, arguments, env, enforce_scope)
        finally:
            if request:
                request._mcp_tool_category = None
