from __future__ import annotations

import hashlib
import secrets
from typing import Any

import psycopg2

from odoo import api, fields, models
from odoo.fields import Domain
from odoo.tools import SQL
from odoo.tools.misc import mute_logger

from odoo.addons.muk_mcp.tools.rate_limit import rate_limiter


class MCPKey(models.Model):
    """Hashed MCP API key with per-key scope and rate limit."""

    _name = 'muk_mcp.key'
    _description = 'MCP API Key'
    _explanation = (
        'An API key an MCP client such as Claude Code or Cursor sends as its '
        'bearer token. It acts as the user who owns it, limited to read-only '
        'tools or allowed to write, and to a number of requests per minute. '
        'Only a hash of the key is stored; the key itself is shown once.'
    )
    _order = 'create_date desc'
    _allow_sudo_commands = False

    # ----------------------------------------------------------
    # Defaults
    # ----------------------------------------------------------

    def _default_rate_limit(self) -> int:
        """Return the configured default requests per minute for a new key."""
        return (
            self.env['ir.config_parameter']
            .sudo()
            .get_int('muk_mcp.rate_limit_requests', 60)
        )

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    name = fields.Char(
        string='Label',
        required=True,
    )

    key_hash = fields.Char(
        string='Key Hash',
        readonly=True,
        required=True,
        index=True,
    )

    key_prefix = fields.Char(
        string='Key Prefix',
        help='First 8 characters of the key for identification.',
        readonly=True,
    )

    user_id = fields.Many2one(
        comodel_name='res.users',
        string='User',
        required=True,
        default=lambda self: self.env.user,
        index=True,
        ondelete='cascade',
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
        default=_default_rate_limit,
    )

    active = fields.Boolean(
        string='Active',
        default=True,
    )

    last_used = fields.Datetime(
        string='Last Used',
        readonly=True,
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @staticmethod
    def _hash_key(key: str) -> str:
        """Return the SHA-256 hex digest used to store and look up an API key."""
        return hashlib.sha256(key.encode()).hexdigest()

    def _check_rate_limit(self) -> bool:
        """Return whether this key is within its per-minute request budget.

        The bucket is keyed by database as well as key id, because the limiter
        is shared by every database the process serves.
        """
        return rate_limiter.check((self.env.cr.dbname, self.id), self.rate_limit, 60)

    @api.model
    def _authenticate_domain(self) -> Domain:
        """Return the domain an authenticating key's owner must satisfy.

        Requires an active user, so archiving a user revokes their keys. Override
        to relax it, e.g. for intentionally inactive service users.
        """
        return Domain('user_id.active', '=', True)

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    def _generate(self, name: str, scope: str, rate_limit: int) -> tuple[MCPKey, str]:
        """Create a key for the current user.

        :return: the key record and its plaintext value, which is never stored
        """
        raw_key = secrets.token_urlsafe(32)
        record = self.sudo().create(
            {
                'name': name,
                'user_id': self.env.uid,
                'key_hash': self._hash_key(raw_key),
                'key_prefix': raw_key[:8],
                'scope': scope,
                'rate_limit': rate_limit,
            },
        )
        return record, raw_key

    @api.model
    def generate_playground_key(
        self,
        name: str | None = None,
        scope: str = 'write',
    ) -> dict[str, Any]:
        """Create a key for the current user and return it with the plaintext.

        :return: key metadata including the one-time ``plaintext`` value
        """
        record, raw_key = self._generate(
            name or 'Playground',
            scope,
            self._default_rate_limit(),
        )
        return {
            'id': record.id,
            'name': record.name,
            'key_prefix': record.key_prefix,
            'scope': record.scope,
            'rate_limit': record.rate_limit,
            'plaintext': raw_key,
        }

    @api.model
    def authenticate(self, token: str) -> MCPKey:
        """Resolve a bearer token to its active key and stamp its last use.

        The stamp tolerates a concurrent request on the same key.

        :return: the matching key, or an empty recordset
        """
        key = self.sudo().search(
            Domain('key_hash', '=', self._hash_key(token))
            & self._authenticate_domain(),
            limit=1,
        )
        if key:
            try:
                with mute_logger('odoo.sql_db'), self.env.cr.savepoint(flush=False):
                    self.env.cr.execute(
                        SQL(
                            "UPDATE %s SET last_used = NOW() AT TIME ZONE 'UTC' "
                            'WHERE id = %s',
                            SQL.identifier(self._table),
                            key.id,
                        ),
                    )
            except psycopg2.Error:
                pass
        return key
