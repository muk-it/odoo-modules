from __future__ import annotations

from odoo import fields, models


class MCPLog(models.Model):
    """Tag MCP tool logs with their source and chat session."""

    _inherit = 'muk_mcp.log'
    _explanation = (
        'A tool call an AI chat made is logged here as well, with the chat it '
        'came from.'
    )

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    source = fields.Selection(
        selection=[
            ('chat', 'Chat'),
            ('mcp', 'MCP'),
        ],
        string='Source',
        readonly=True,
        required=True,
        default='mcp',
        index=True,
    )

    session_id = fields.Many2one(
        comodel_name='muk_ai.session',
        string='Chat Session',
        readonly=True,
        index=True,
        ondelete='cascade',
    )
