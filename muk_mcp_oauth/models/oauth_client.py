# Copyright 2026, Jarsa
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl.html).

import uuid
from datetime import timedelta
from urllib.parse import urlparse

from odoo import api, fields, models

ALLOWED_HOSTS = ("claude.ai", "claude.com")
LOOPBACK_HOSTS = ("localhost", "127.0.0.1")
CLIENT_IDLE_DAYS = 60


class OAuthClient(models.Model):
    _name = "muk_mcp.oauth.client"
    _description = "OAuth 2.1 Client (RFC 7591 Dynamic Client Registration)"
    _order = "id desc"

    client_id = fields.Char(
        required=True,
        readonly=True,
        index=True,
        copy=False,
        default=lambda self: str(uuid.uuid4()),
    )
    client_name = fields.Char(required=True)
    redirect_uris = fields.Text(
        required=True,
        help="Registered redirect URIs, one per line.",
    )
    last_used = fields.Datetime(readonly=True)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("client_id_uniq", "unique(client_id)", "The client_id must be unique."),
    ]

    @api.model
    def _is_uri_allowed(self, uri):
        """Hard whitelist: https on claude.ai/claude.com hosts, or plain http
        on the loopback interface (RFC 8252 native clients)."""
        try:
            parsed = urlparse(uri)
        except ValueError:
            return False
        if parsed.scheme == "https" and parsed.hostname in ALLOWED_HOSTS:
            return True
        return parsed.scheme == "http" and parsed.hostname in LOOPBACK_HOSTS

    def _uri_list(self):
        self.ensure_one()
        return [uri.strip() for uri in (self.redirect_uris or "").splitlines() if uri.strip()]

    def _match_redirect_uri(self, uri):
        """Exact match against the registered URIs; the port is ignored only
        for loopback URIs (RFC 8252 §7.3, Claude Code uses ephemeral ports)."""
        self.ensure_one()
        if not uri or not self._is_uri_allowed(uri):
            return False
        requested = urlparse(uri)
        for registered_uri in self._uri_list():
            if registered_uri == uri:
                return True
            registered = urlparse(registered_uri)
            if (
                registered.scheme == requested.scheme == "http"
                and registered.hostname in LOOPBACK_HOSTS
                and requested.hostname == registered.hostname
                and requested.path == registered.path
                and requested.query == registered.query
            ):
                return True
        return False

    @api.model
    def _gc_clients(self):
        """Cron: archive DCR clients idle for more than 60 days that hold no
        live token (Claude registers a fresh client per connection, so the
        table grows without this)."""
        cutoff = fields.Datetime.now() - timedelta(days=CLIENT_IDLE_DAYS)
        idle = self.search(
            [
                ("create_date", "<", cutoff),
                "|",
                ("last_used", "=", False),
                ("last_used", "<", cutoff),
            ]
        )
        live = self.env["muk_mcp.oauth.token"].search([("client_id", "in", idle.ids), ("revoked", "=", False)]).client_id
        (idle - live).write({"active": False})
