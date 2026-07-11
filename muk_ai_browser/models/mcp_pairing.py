from __future__ import annotations

import secrets

from odoo import api, fields, models
from odoo.tools import SQL


class MCPPairing(models.Model):
    """Single-use pairing code that mints a device key for a browser extension."""

    _name = 'muk_mcp.pairing'
    _description = 'MCP Device Pairing Code'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    code_hash = fields.Char(
        string='Code Hash',
        required=True,
        index=True,
        copy=False,
    )

    code_prefix = fields.Char(
        string='Code Prefix',
    )

    user_id = fields.Many2one(
        comodel_name='res.users',
        string='User',
        required=True,
        ondelete='cascade',
    )

    device_label = fields.Char(
        string='Device Label',
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

    expires_at = fields.Datetime(
        string='Expires At',
        index=True,
    )

    used = fields.Boolean(
        string='Used',
        default=False,
    )

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    def _pairing_ttl(self) -> int:
        """Return the pairing-code lifetime in seconds from the config parameter."""
        return int(
            self.env['ir.config_parameter']
            .sudo()
            .get_param(
                'muk_ai_browser.pairing_ttl',
                120,
            ),
        )

    @api.model
    def _mint_code(
        self,
        user_id: int,
        device_label: str | None = None,
        scope: str = 'write',
    ) -> str:
        """Create a single-use pairing code bound to a user and return the plaintext.

        The code is stored hashed; the cleartext is returned exactly once so the
        browser extension can exchange it for a device key.

        :return: the cleartext pairing code
        """
        code = secrets.token_urlsafe(24)
        expires_at = fields.Datetime.add(
            fields.Datetime.now(),
            seconds=self._pairing_ttl(),
        )
        self.sudo().create(
            {
                'code_hash': self.env['muk_mcp.key']._hash_key(code),
                'code_prefix': code[:8],
                'user_id': user_id,
                'device_label': device_label,
                'scope': scope,
                'expires_at': expires_at,
                'used': False,
            },
        )
        return code

    @api.model
    def _consume(self, code: str) -> dict | None:
        """Atomically redeem an unused, unexpired pairing code exactly once.

        Uses a single conditional ``UPDATE ... RETURNING`` so two concurrent
        requests can never redeem the same code.

        :return: ``{user_id, device_label, scope}`` on success, or ``None`` when
            the code is unknown, already used or expired
        """
        if not code:
            return None
        self.flush_model(['code_hash', 'used', 'expires_at'])
        self.env.cr.execute(
            SQL(
                """
            UPDATE %s SET used = true
             WHERE code_hash = %s AND used = false AND expires_at > (now() AT TIME ZONE 'UTC')
            RETURNING user_id, device_label, scope
            """,
                SQL.identifier(self._table),
                self.env['muk_mcp.key']._hash_key(code),
            ),
        )
        if not (row := self.env.cr.fetchone()):
            return None
        return {
            'user_id': row[0],
            'device_label': row[1],
            'scope': row[2],
        }

    # ----------------------------------------------------------
    # Cron
    # ----------------------------------------------------------

    @api.model
    def _gc(self) -> None:
        """Delete used or expired pairing codes."""
        self.sudo().search(
            [
                '|',
                ('used', '=', True),
                ('expires_at', '<', fields.Datetime.now()),
            ],
        ).unlink()
