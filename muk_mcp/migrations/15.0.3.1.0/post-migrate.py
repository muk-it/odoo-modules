from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Drop the chatter tools the database held, which shadow the shipped methods."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    for name in ('tool_get_messages', 'tool_post_message'):
        if tool := env.ref(f'muk_mcp.{name}', raise_if_not_found=False):
            tool.unlink()
