from __future__ import annotations

from typing import Any

from odoo import fields, models

from odoo.addons.base.models.res_users import check_identity


class ResUsers(models.Model):
    """Add the user's MCP keys and the action to create one."""

    _inherit = 'res.users'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    mcp_key_ids = fields.One2many(
        comodel_name='muk_mcp.key',
        inverse_name='user_id',
        string='MCP Keys',
    )

    # ----------------------------------------------------------
    # Actions
    # ----------------------------------------------------------

    @check_identity
    def action_generate_mcp_key(self) -> dict[str, Any]:
        """Open the wizard to generate a new MCP key for this user."""
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('New MCP Key'),
            'res_model': 'muk_mcp.generate_key',
            'views': [(False, 'form')],
            'target': 'new',
        }
