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

    def _message_format(self, fnames, format_reply=True):
        vals_list = super()._message_format(fnames, format_reply=format_reply)
        by_id = {message.id: message for message in self}
        for vals in vals_list:
            message = by_id.get(vals.get('id'))
            vals['mcp_name'] = (message.mcp_name if message else False) or False
        return vals_list

    # ----------------------------------------------------------
    # ORM
    # ----------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        if mcp_name := self.env.context.get('mcp_name'):
            for vals in vals_list:
                vals.setdefault('mcp_name', mcp_name)
        return super().create(vals_list)
