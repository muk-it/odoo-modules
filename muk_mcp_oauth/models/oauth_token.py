# Copyright 2026, Jarsa
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl.html).

import secrets
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError

ACCESS_TTL_SECONDS = 3600
REFRESH_TTL_DAYS = 30
ABSOLUTE_TTL_DAYS = 180


class OAuthToken(models.Model):
    _name = "muk_mcp.oauth.token"
    _description = "OAuth 2.1 Access/Refresh Token"
    _order = "id desc"

    access_token_hash = fields.Char(required=True, readonly=True, index=True)
    refresh_token_hash = fields.Char(required=True, readonly=True, index=True)
    client_id = fields.Many2one(
        comodel_name="muk_mcp.oauth.client",
        required=True,
        readonly=True,
        index=True,
        ondelete="cascade",
    )
    user_id = fields.Many2one(
        comodel_name="res.users",
        required=True,
        readonly=True,
        index=True,
        ondelete="cascade",
    )
    mcp_key_id = fields.Many2one(
        comodel_name="muk_mcp.key",
        readonly=True,
        index=True,
        ondelete="cascade",
        help="MCP key materializing the access token: the /mcp Bearer "
        "resolver, scope gating, rate limiting and audit logging of muk_mcp "
        "operate on this key without any patch.",
    )
    scope = fields.Char(readonly=True)
    client_name = fields.Char(related="client_id.client_name")
    access_expiration = fields.Datetime(required=True, readonly=True)
    refresh_expiration = fields.Datetime(required=True, readonly=True)
    absolute_expiration = fields.Datetime(
        required=True,
        readonly=True,
        help="Hard cap of the whole refresh chain (180 days). "
        "Enforced by the refresh_token grant.",
    )
    revoked = fields.Boolean()
    last_used = fields.Datetime(readonly=True)
    last_ip = fields.Char(readonly=True)

    @api.model
    def _issue(self, client, user, scope):
        """Issue an access/refresh token pair for an authorized user.

        Returns (token record, plaintext access token, plaintext refresh
        token). Only SHA-256 hashes are stored.
        """
        access_raw = secrets.token_urlsafe(32)
        refresh_raw = secrets.token_urlsafe(32)
        key_model = self.env["muk_mcp.key"].sudo()
        rate_limit = int(self.env["ir.config_parameter"].sudo().get_param("muk_mcp.rate_limit_requests", 60))
        key = key_model.create(
            {
                "name": f"{client.client_name} (OAuth)",
                "user_id": user.id,
                "key_hash": key_model._hash_key(access_raw),
                "key_prefix": access_raw[:8],
                "scope": "write" if "mcp:write" in (scope or "").split() else "read",
                "rate_limit": rate_limit,
            }
        )
        now = fields.Datetime.now()
        token = self.create(
            {
                "access_token_hash": key_model._hash_key(access_raw),
                "refresh_token_hash": key_model._hash_key(refresh_raw),
                "client_id": client.id,
                "user_id": user.id,
                "mcp_key_id": key.id,
                "scope": scope,
                "access_expiration": now + timedelta(seconds=ACCESS_TTL_SECONDS),
                "refresh_expiration": now + timedelta(days=REFRESH_TTL_DAYS),
                "absolute_expiration": now + timedelta(days=ABSOLUTE_TTL_DAYS),
            }
        )
        return token, access_raw, refresh_raw

    @api.model
    def _refresh(self, raw_refresh, client):
        """Rotate a refresh token (OAuth 2.1 mandatory rotation for public
        clients): the old access and refresh tokens stop working in the same
        response. Rotation happens in place, so the linked MCP key keeps its
        identity (audit log continuity) with a new hash.

        Returns (token, access_raw, refresh_raw), empty/None when the
        refresh token is unknown, revoked or past its expiration or the
        180-day absolute cap.
        """
        key_model = self.env["muk_mcp.key"].sudo()
        token = self.search(
            [
                ("refresh_token_hash", "=", key_model._hash_key(raw_refresh or "")),
                ("client_id", "=", client.id),
            ],
            limit=1,
        )
        now = fields.Datetime.now()
        if not token or token.revoked or token.refresh_expiration < now or token.absolute_expiration < now:
            return self.browse(), None, None
        access_raw = secrets.token_urlsafe(32)
        refresh_raw = secrets.token_urlsafe(32)
        token.mcp_key_id.write(
            {
                "key_hash": key_model._hash_key(access_raw),
                "key_prefix": access_raw[:8],
            }
        )
        # authenticate() reads the key table with raw SQL, so the rotated
        # hash must hit the database within this transaction.
        token.mcp_key_id.flush_recordset()
        token.write(
            {
                "access_token_hash": key_model._hash_key(access_raw),
                "refresh_token_hash": key_model._hash_key(refresh_raw),
                "access_expiration": now + timedelta(seconds=ACCESS_TTL_SECONDS),
                "refresh_expiration": min(now + timedelta(days=REFRESH_TTL_DAYS), token.absolute_expiration),
            }
        )
        return token, access_raw, refresh_raw

    @api.model
    def _revoke_value(self, raw_token):
        """RFC 7009: revoke by plaintext access or refresh token. Unknown
        values are ignored (the endpoint answers 200 regardless)."""
        token_hash = self.env["muk_mcp.key"]._hash_key(raw_token or "")
        self.search(
            [
                "|",
                ("access_token_hash", "=", token_hash),
                ("refresh_token_hash", "=", token_hash),
            ]
        ).action_revoke()

    def action_revoke(self):
        if not self.env.su and not self.env.user.has_group("base.group_system"):
            if any(token.user_id != self.env.user for token in self):
                raise AccessError(_("You can only revoke your own OAuth connections."))
        self.sudo().write({"revoked": True})
        self.sudo().mcp_key_id.write({"active": False})

    @api.model
    def _gc_tokens(self):
        """Cron: purge revoked tokens and tokens past their refresh or
        absolute expiration (their MCP keys go with them via unlink)."""
        now = fields.Datetime.now()
        self.search(
            [
                "|",
                "|",
                ("revoked", "=", True),
                ("refresh_expiration", "<", now),
                ("absolute_expiration", "<", now),
            ]
        ).unlink()

    def unlink(self):
        # The MCP key materializes the access token: it must never outlive
        # the OAuth token record (an orphan key would keep authenticating
        # with the 180-day default policy instead of the 60-minute TTL).
        keys = self.mcp_key_id
        res = super().unlink()
        keys.sudo().unlink()
        return res
