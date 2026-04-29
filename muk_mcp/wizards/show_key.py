from odoo import fields, models


class MCPKeyShow(models.AbstractModel):

    _name = 'muk_mcp.key.show'
    _description = "Show MCP Key"

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    id = fields.Id(
        string="ID",
    )

    key = fields.Char(
        string="API Key",
        readonly=True,
    )
