from __future__ import annotations

from typing import Any

from odoo import fields, models


class MCPKeyWizard(models.TransientModel):
    """Wizard collecting key metadata and creating a new MCP API key."""

    _name = 'muk_mcp.generate_key'
    _description = 'MCP Generate Key'
    _explanation = (
        'A wizard that creates an MCP API key for the current user with a '
        'label, a scope and a rate limit.'
    )
    _transient_max_hours = 0.1

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    name = fields.Char(
        string='Description',
        required=True,
    )

    scope = fields.Selection(
        selection=[
            ('read', 'Read Only'),
            ('write', 'Read & Write'),
        ],
        string='Scope',
        required=True,
        default='write',
    )

    rate_limit = fields.Integer(
        string='Rate Limit (req/min)',
        help='Maximum requests per minute. 0 = unlimited.',
        default=lambda self: self.env['muk_mcp.key']._default_rate_limit(),
    )

    # ----------------------------------------------------------
    # Actions
    # ----------------------------------------------------------

    def action_make_key(self) -> dict[str, Any]:
        """Create the API key and open the dialog that reveals it once."""
        self.ensure_one()
        _key, raw_key = self.env['muk_mcp.key']._generate(
            self.name,
            self.scope,
            self.rate_limit,
        )
        self.unlink()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('MCP Key Ready'),
            'res_model': 'muk_mcp.key.show',
            'views': [(False, 'form')],
            'target': 'new',
            'context': {'default_key': raw_key},
        }
