import hashlib
import time

from odoo import api, fields, models
from odoo.tools import SQL

_rate_limit_store = {}


class MCPKey(models.Model):

    _name = 'muk_mcp.key'
    _description = "MCP API Key"
    _auto = False

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    name = fields.Char(
        string="Label",
        required=True,
    )

    key_hash = fields.Char(
        string="Key Hash",
        readonly=True,
        index=True,
    )

    key_prefix = fields.Char(
        string="Key Prefix",
        readonly=True,
        help="First 8 characters of the key for identification.",
    )

    user_id = fields.Many2one(
        comodel_name='res.users',
        string="User",
        required=True,
        default=lambda self: self.env.user,
        index=True,
        ondelete='cascade',
    )

    scope_ids = fields.One2many(
        comodel_name='muk_mcp.scope',
        inverse_name='key_id',
        string="Model Scopes",
    )

    rate_limit = fields.Integer(
        string="Rate Limit (req/min)",
        default=60,
        help="Maximum requests per minute. 0 = unlimited.",
    )

    active = fields.Boolean(
        string="Active",
        default=True,
    )

    last_used = fields.Datetime(
        string="Last Used",
        readonly=True,
    )

    create_date = fields.Datetime(
        string="Created",
        readonly=True,
    )

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    def init(self):
        self.env.cr.execute(SQL(
            """
            CREATE TABLE IF NOT EXISTS %s (
                id SERIAL PRIMARY KEY,
                name VARCHAR NOT NULL,
                key_hash VARCHAR(64) NOT NULL,
                key_prefix VARCHAR(8),
                user_id INTEGER NOT NULL REFERENCES res_users(id) ON DELETE CASCADE,
                rate_limit INTEGER DEFAULT 60,
                active BOOLEAN DEFAULT true,
                last_used TIMESTAMP WITHOUT TIME ZONE,
                create_date TIMESTAMP WITHOUT TIME ZONE DEFAULT (now() AT TIME ZONE 'UTC'),
                write_date TIMESTAMP WITHOUT TIME ZONE DEFAULT (now() AT TIME ZONE 'UTC'),
                create_uid INTEGER REFERENCES res_users(id) ON DELETE SET NULL,
                write_uid INTEGER REFERENCES res_users(id) ON DELETE SET NULL
            )
            """,
            SQL.identifier(self._table),
        ))
        self.env.cr.execute(SQL(
            "CREATE INDEX IF NOT EXISTS %s ON %s (key_hash)",
            SQL.identifier(f'{self._table}_key_hash_idx'),
            SQL.identifier(self._table),
        ))

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @staticmethod
    def _hash_key(key):
        return hashlib.sha256(key.encode()).hexdigest()

    def _check_rate_limit(self):
        if not self.rate_limit:
            return True
        now = time.time()
        window = 60
        store_key = self.id
        timestamps = _rate_limit_store.get(store_key, [])
        timestamps = [t for t in timestamps if now - t < window]
        if len(timestamps) >= self.rate_limit:
            _rate_limit_store[store_key] = timestamps
            return False
        timestamps.append(now)
        _rate_limit_store[store_key] = timestamps
        return True

    def _check_model_access(self, model_name, operation='read'):
        if not self.scope_ids:
            return True
        scope = self.scope_ids.filtered(
            lambda s: s.model_id.model == model_name
        )
        perm_map = {
            'read': 'perm_read',
            'write': 'perm_write',
            'create': 'perm_create',
            'unlink': 'perm_unlink',
        }
        field_name = perm_map.get(operation)
        return bool(scope and field_name and scope[0][field_name])

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    def authenticate(self, token):
        table = SQL.identifier(self._table)
        self.env.cr.execute(SQL(
            """
            SELECT id FROM %s
            WHERE key_hash = %s AND active = true
            LIMIT 1
            """,
            table,
            self._hash_key(token),
        ))
        row = self.env.cr.fetchone()
        if not row:
            return None
        cr = self.env.cr
        try:
            cr.execute("SAVEPOINT key_touch")
            cr.execute(SQL(
                """
                UPDATE %s
                SET last_used = NOW() AT TIME ZONE 'UTC'
                WHERE id = %s
                """,
                table,
                row[0],
            ))
            cr.execute("RELEASE SAVEPOINT key_touch")
        except Exception:
            cr.execute("ROLLBACK TO SAVEPOINT key_touch")
        return self.sudo().browse(row[0])
