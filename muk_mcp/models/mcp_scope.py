from odoo import fields, models


class McpScope(models.Model):

    _name = 'muk_mcp.scope'
    _description = "MCP Model Scope"
    _order = 'model_name'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    key_id = fields.Many2one(
        comodel_name='muk_mcp.key',
        string="API Key",
        required=True,
        index=True,
        ondelete='cascade',
    )

    model_name = fields.Char(
        string="Model",
        required=True,
        help="Technical model name (e.g. 'res.partner', 'sale.order').",
    )

    perm_read = fields.Boolean(
        string="Read",
        default=True,
    )

    perm_write = fields.Boolean(
        string="Write",
        default=False,
    )

    perm_create = fields.Boolean(
        string="Create",
        default=False,
    )

    perm_unlink = fields.Boolean(
        string="Delete",
        default=False,
    )
