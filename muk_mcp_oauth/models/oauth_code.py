# Copyright 2026, Jarsa
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl.html).

import base64
import hashlib
import hmac
import secrets
from datetime import timedelta

from odoo import api, fields, models

CODE_TTL_SECONDS = 120


class OAuthCode(models.Model):
    _name = "muk_mcp.oauth.code"
    _description = "OAuth 2.1 Authorization Code"
    _order = "id desc"

    code_hash = fields.Char(required=True, readonly=True, index=True)
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
    scope = fields.Char(readonly=True)
    code_challenge = fields.Char(required=True, readonly=True)
    redirect_uri = fields.Char(required=True, readonly=True)
    expiration = fields.Datetime(required=True, readonly=True)
    used = fields.Boolean()

    @api.model
    def _issue(self, client, user, scope, code_challenge, redirect_uri):
        """Create a single-use authorization code and return its plaintext."""
        raw_code = secrets.token_urlsafe(32)
        self.create(
            {
                "code_hash": self.env["muk_mcp.key"]._hash_key(raw_code),
                "client_id": client.id,
                "user_id": user.id,
                "scope": scope,
                "code_challenge": code_challenge,
                "redirect_uri": redirect_uri,
                "expiration": fields.Datetime.now() + timedelta(seconds=CODE_TTL_SECONDS),
            }
        )
        return raw_code

    @api.model
    def _consume(self, raw_code, client, redirect_uri, code_verifier):
        """Validate and burn an authorization code (single use, TTL, exact
        redirect_uri, PKCE S256). Returns the code record or an empty
        recordset when any check fails."""
        code = self.search(
            [
                ("code_hash", "=", self.env["muk_mcp.key"]._hash_key(raw_code or "")),
                ("client_id", "=", client.id),
            ],
            limit=1,
        )
        if not code or code.used:
            return self.browse()
        # Burn before the remaining checks: a code that reaches the token
        # endpoint is spent no matter the outcome (OAuth 2.1 single use).
        code.used = True
        if code.expiration < fields.Datetime.now():
            return self.browse()
        if code.redirect_uri != redirect_uri:
            return self.browse()
        if not code_verifier:
            return self.browse()
        digest = hashlib.sha256(code_verifier.encode()).digest()
        challenge = base64.urlsafe_b64encode(digest).decode().rstrip("=")
        if not hmac.compare_digest(challenge, code.code_challenge):
            return self.browse()
        return code

    @api.model
    def _gc_codes(self):
        """Cron: purge consumed codes and codes past their 120s TTL."""
        self.search(["|", ("used", "=", True), ("expiration", "<", fields.Datetime.now())]).unlink()
