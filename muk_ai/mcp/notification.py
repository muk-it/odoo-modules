from __future__ import annotations

from odoo import api, models

from odoo.addons.muk_mcp.core.tool import mcp_tool


class AINotification(models.AbstractModel):
    """Expose the in-client toast notification as an MCP tool."""

    _inherit = 'muk_mcp.mixin'

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    @mcp_tool(
        name='show_notification',
        description=(
            'Show a toast notification to the user in the Odoo web '
            'client. Use for short status messages, warnings, or '
            'confirmations that do not require navigating away. '
            '"type" is forwarded to the display_notification client '
            'action and controls colour: typically "info" (blue), '
            '"success" (green), "warning" (yellow), "danger" (red). '
            'AI-agent only.'
        ),
        input_schema={
            'type': 'object',
            'properties': {
                'message': {
                    'type': 'string',
                    'description': 'The message body.',
                },
                'title': {
                    'type': 'string',
                    'description': 'Optional short title.',
                },
                'type': {
                    'type': 'string',
                    'description': (
                        'Notification style passed to display_notification. '
                        'Default: "info".'
                    ),
                    'default': 'info',
                },
                'sticky': {
                    'type': 'boolean',
                    'description': ('If true, the user must dismiss it manually.'),
                    'default': False,
                },
            },
            'required': ['message'],
        },
        category='read',
        registry='odoo',
    )
    def _mcp_show_notification(
        self,
        message,
        title=None,
        type='info',
        sticky=False,
    ) -> dict:
        """Return a ``display_notification`` client action descriptor."""
        params = {
            'message': message,
            'type': type,
            'sticky': bool(sticky),
        }
        if title:
            params['title'] = title
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': params,
        }
