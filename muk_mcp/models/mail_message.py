from odoo import fields, models
from odoo.addons.mail.tools.discuss import Store


class MailMessage(models.Model):

    _inherit = 'mail.message'

    mcp_key_name = fields.Char(
        string="MCP Key",
        readonly=True,
    )

    def _to_store_defaults(self, target):
        return super()._to_store_defaults(target) + ['mcp_key_name']
