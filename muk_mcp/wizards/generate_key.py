from __future__ import annotations

import secrets
from typing import Any

from odoo import _, fields, models


class MCPKeyWizard(models.TransientModel):
    """Wizard collecting key metadata and creating a new MCP API key."""

    _name = 'muk_mcp.generate_key'
    _description = 'MCP Generate Key'
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
        default=lambda self: int(
            self.env['ir.config_parameter']
            .sudo()
            .get_param(
                'muk_mcp.rate_limit_requests',
                60,
            ),
        ),
        help='Maximum requests per minute. 0 = unlimited.',
    )

    # ----------------------------------------------------------
    # Actions
    # ----------------------------------------------------------

    def action_make_key(self) -> dict[str, Any]:
        """Create the API key from the wizard and open the one-time reveal dialog.

        :return: A window action showing the plaintext key, available only once.
        """
        self.ensure_one()
        raw_key = secrets.token_urlsafe(32)
        key_model = self.env['muk_mcp.key']
        key_model.sudo().create(
            {
                'name': self.name,
                'user_id': self.env.uid,
                'key_hash': key_model._hash_key(raw_key),
                'key_prefix': raw_key[:8],
                'scope': self.scope,
                'rate_limit': self.rate_limit,
            },
        )
        self.unlink()
        return {
            'type': 'ir.actions.act_window',
            'name': _('MCP Key Ready'),
            'res_model': 'muk_mcp.key.show',
            'views': [(False, 'form')],
            'target': 'new',
            'context': {'default_key': raw_key},
        }
