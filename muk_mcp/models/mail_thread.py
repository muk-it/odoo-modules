from markupsafe import Markup, escape

from odoo import models


class MailThread(models.AbstractModel):

    _inherit = 'mail.thread'

    def message_post(self, *, body='', **kwargs):
        ctx = self.env.context
        if ctx.get('mcp_via') and body:
            key_name = ctx.get('mcp_key_name', 'MCP')
            tag = f' \u2014 via MCP: {key_name}'
            if isinstance(body, Markup):
                body = body + Markup(escape(tag))
            elif isinstance(body, str):
                body = f'{body}{tag}'
        return super().message_post(body=body, **kwargs)
