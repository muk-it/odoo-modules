from __future__ import annotations

import secrets

from odoo import api, fields, models


class BrowserDevice(models.Model):
    """Paired browser device backed by a hashed MuK MCP API key."""

    _name = 'muk_ai_browser.device'
    _description = 'MuK AI Browser Device'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    name = fields.Char(
        string='Label',
        required=True,
    )

    key_id = fields.Many2one(
        comodel_name='muk_mcp.key',
        string='Device Key',
        required=True,
        index=True,
        ondelete='cascade',
    )

    user_id = fields.Many2one(
        comodel_name='res.users',
        related='key_id.user_id',
        string='User',
        readonly=True,
        store=True,
        index=True,
    )

    key_prefix = fields.Char(
        related='key_id.key_prefix',
        string='Key',
        readonly=True,
    )

    user_agent = fields.Char(
        string='User Agent',
        readonly=True,
    )

    last_seen_ip = fields.Char(
        string='Last Seen IP',
        readonly=True,
    )

    last_seen = fields.Datetime(
        string='Last Seen',
        readonly=True,
    )

    active = fields.Boolean(
        related='key_id.active',
        string='Active',
        readonly=True,
        store=True,
    )

    # ----------------------------------------------------------
    # Actions
    # ----------------------------------------------------------

    def action_revoke(self) -> None:
        """Deactivate the backing API key so the device can no longer authenticate."""
        self.sudo().mapped('key_id').write({'active': False})

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    def _mint(
        self,
        user_id: int,
        label: str | None,
        scope: str = 'write',
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> tuple[models.BaseModel, str]:
        """Mint a device API key and create the matching device row.

        :return: the created ``muk_mcp.key`` record and its one-time plaintext
        """
        raw = secrets.token_urlsafe(32)
        Key = self.env['muk_mcp.key']
        rate_limit = int(
            self.env['ir.config_parameter']
            .sudo()
            .get_param(
                'muk_mcp.rate_limit_requests',
                60,
            ),
        )
        key = Key.sudo().create(
            {
                'name': label or 'Browser',
                'user_id': user_id,
                'key_hash': Key._hash_key(raw),
                'key_prefix': raw[:8],
                'scope': scope,
                'rate_limit': rate_limit,
            },
        )
        self.sudo().create(
            {
                'name': label or 'Browser',
                'key_id': key.id,
                'user_agent': user_agent,
                'last_seen_ip': ip_address,
            },
        )
        return key, raw
