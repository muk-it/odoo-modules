from odoo import models


class MailThread(models.AbstractModel):

    _inherit = 'mail.thread'

    def _get_message_create_valid_field_names(self):
        return super()._get_message_create_valid_field_names() | {
            'mcp_key_name',
        }

    def message_post(self, *, body='', **kwargs):
        ctx = self.env.context
        if ctx.get('mcp_via'):
            kwargs.setdefault(
                'mcp_key_name', ctx.get('mcp_key_name', 'MCP'),
            )
        return super().message_post(body=body, **kwargs)
