from __future__ import annotations

from odoo import api, fields, models, modules


class MCPLog(models.Model):
    """Tag MCP tool logs with their source and chat session."""

    _inherit = 'muk_mcp.log'

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

    # ----------------------------------------------------------
    # ORM
    # ----------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list: list[dict]) -> MCPLog:
        """Default ``session_id`` and ``source`` from the context when present."""
        ctx = self.env.context
        session_id = ctx.get('muk_mcp_session_id')
        if session_id:
            vals_list = [
                {
                    **v,
                    'session_id': v.get('session_id') or session_id,
                    'source': v.get('source') or 'chat',
                }
                for v in vals_list
            ]
        return super().create(vals_list)

    @api.model
    def log(self, **values) -> None:
        """Persist a log entry, creating it synchronously during tests."""
        if modules.module.current_test:
            self.sudo().create(values)
            return
        super().log(**values)
