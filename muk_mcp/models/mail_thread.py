from odoo import models


class MailThread(models.AbstractModel):

    _inherit = 'mail.thread'

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _get_message_create_valid_field_names(self):
        return super()._get_message_create_valid_field_names() | {
            'mcp_name',
        }

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    def message_post(self, *, body='', **kwargs):
        if self.env.context.get('mcp_name'):
            kwargs.setdefault('mcp_name', self.env.context['mcp_name'])
        return super().message_post(body=body, **kwargs)
