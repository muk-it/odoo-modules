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

    def _to_store(self, store, /, *, fields=None, **kwargs):
        super()._to_store(store, fields=fields, **kwargs)
        if fields is None:
            for message in self:
                store.add(message, {'mcp_name': message.mcp_name})

    # ----------------------------------------------------------
    # ORM
    # ----------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        if mcp_name := self.env.context.get('mcp_name'):
            for vals in vals_list:
                vals.setdefault('mcp_name', mcp_name)
        return super().create(vals_list)
