from odoo import api, fields, models


class MailMessage(models.Model):

    _inherit = 'mail.message'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    mcp_name = fields.Char(
        string="MCP Key",
        readonly=True,
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _to_store_defaults(self, target):
        return super()._to_store_defaults(target) + ['mcp_name']

    # ----------------------------------------------------------
    # ORM
    # ----------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        if mcp_name := self.env.context.get('mcp_name'):
            for vals in vals_list:
                vals.setdefault('mcp_name', mcp_name)
        return super().create(vals_list)
