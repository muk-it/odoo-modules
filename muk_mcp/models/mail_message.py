from odoo import fields, models


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
