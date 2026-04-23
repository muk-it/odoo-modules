from odoo import fields, models


class MCPTool(models.Model):

    _inherit = 'muk_mcp.tool'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    registry = fields.Selection(
        selection_add=[('odoo', "Odoo")],
        ondelete={'odoo': 'set null'},
    )
