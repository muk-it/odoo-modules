from odoo import api, fields, models


class MCPTool(models.Model):

    _inherit = 'muk_mcp.tool'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    registry = fields.Selection(
        selection_add=[('odoo', "Odoo")],
        ondelete={'odoo': 'set null'},
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _tool_log_values(self, **kwargs):
        values = super()._tool_log_values(**kwargs)
        ctx = self.env.context
        if session_id := ctx.get('muk_mcp_session_id'):
            values['session_id'] = session_id
            values['source'] = 'chat'
        else:
            values.setdefault('source', 'mcp')
        return values
