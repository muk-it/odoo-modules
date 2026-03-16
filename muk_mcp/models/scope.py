from odoo import fields, models


class MCPScope(models.Model):

    _name = 'muk_mcp.scope'
    _description = "MCP Model Scope"
    _order = 'model_id'

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

    model_id = fields.Many2one(
        comodel_name='ir.model',
        string="Model",
        required=True,
        ondelete='cascade',
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
