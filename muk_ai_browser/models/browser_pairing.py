from __future__ import annotations

import secrets

from odoo import api, fields, models
from odoo.tools import SQL


class BrowserPairing(models.Model):
    """One-time code a browser extension exchanges for its API key."""

    _name = 'muk_ai_browser.pairing'
    _description = 'Browser Pairing Code'
    _explanation = (
        'A short-lived, single-use code shown on the "Connect a browser" page. '
        'The browser extension exchanges it for an API key of the user who '
        'opened the page. Only a hash of the code is stored.'
    )

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    code_hash = fields.Char(
        string='Code Hash',
        required=True,
        index=True,
    )

    user_id = fields.Many2one(
        comodel_name='res.users',
        string='User',
        required=True,
        ondelete='cascade',
    )

    expires_at = fields.Datetime(
        string='Expires At',
        required=True,
    )

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    def _pairing_ttl(self) -> int:
        """Return how many seconds a pairing code stays valid."""
        return (
            self.env['ir.config_parameter']
            .sudo()
            .get_int('muk_ai_browser.pairing_ttl', 300)
        )

    @api.model
    def _mint(self) -> str:
        """Create a pairing code for the current user and return it once."""
        code = secrets.token_urlsafe(24)
        self.sudo().create(
            {
                'code_hash': self.env['muk_mcp.key']._hash_key(code),
                'user_id': self.env.uid,
                'expires_at': fields.Datetime.add(
                    fields.Datetime.now(), seconds=self._pairing_ttl()
                ),
            }
        )
        return code

    @api.model
    def _redeem(self, code: str | None) -> models.BaseModel:
        """Consume a valid code exactly once and return its user, else no user."""
        if not code:
            return self.env['res.users']
        self.flush_model()
        self.env.cr.execute(
            SQL(
                'DELETE FROM %s WHERE code_hash = %s AND expires_at > NOW() AT TIME '
                "ZONE 'UTC' RETURNING user_id",
                SQL.identifier(self._table),
                self.env['muk_mcp.key']._hash_key(code),
            )
        )
        row = self.env.cr.fetchone()
        return self.env['res.users'].browse(row[0] if row else ())

    # ----------------------------------------------------------
    # Cron
    # ----------------------------------------------------------

    @api.autovacuum
    def _gc_expired(self) -> None:
        """Delete the codes nobody redeemed in time."""
        self.sudo().search(
            [('expires_at', '<', fields.Datetime.now())],
        ).unlink()
