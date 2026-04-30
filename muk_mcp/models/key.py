import hashlib
import secrets

from odoo import api, fields, models
from odoo.tools.misc import mute_logger

from odoo.addons.muk_mcp.tools.rate_limit import rate_limiter


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

    scope = fields.Selection(
        selection=[
            ('read', "Read Only"),
            ('write', "Read & Write"),
        ],
        string="Scope",
        required=True,
        default='write',
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
        self.env.cr.execute(f"""
            CREATE TABLE IF NOT EXISTS {self._table} (
                id SERIAL PRIMARY KEY,
                name VARCHAR NOT NULL,
                key_hash VARCHAR(64) NOT NULL,
                key_prefix VARCHAR(8),
                user_id INTEGER NOT NULL REFERENCES res_users(id) ON DELETE CASCADE,
                scope VARCHAR DEFAULT 'write',
                rate_limit INTEGER DEFAULT 60,
                active BOOLEAN DEFAULT true,
                last_used TIMESTAMP WITHOUT TIME ZONE,
                create_date TIMESTAMP WITHOUT TIME ZONE DEFAULT (now() AT TIME ZONE 'UTC'),
                write_date TIMESTAMP WITHOUT TIME ZONE DEFAULT (now() AT TIME ZONE 'UTC'),
                create_uid INTEGER REFERENCES res_users(id) ON DELETE SET NULL,
                write_uid INTEGER REFERENCES res_users(id) ON DELETE SET NULL
            )
        """)
        self.env.cr.execute(
            f"CREATE INDEX IF NOT EXISTS {self._table}_key_hash_idx "
            f"ON {self._table} (key_hash)"
        )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @staticmethod
    def _hash_key(key):
        return hashlib.sha256(key.encode()).hexdigest()

    def _check_rate_limit(self, count=1):
        return rate_limiter.check(
            self.id, self.rate_limit, 60, count=count,
        )

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    def generate_connect_key(self, name=None, scope='write'):
        rate_limit = int(self.env['ir.config_parameter'].sudo().get_param(
            'muk_mcp.rate_limit_requests', 60,
        ))
        raw_key = secrets.token_urlsafe(32)
        record = self.sudo().create({
            'name': name or 'Playground',
            'user_id': self.env.uid,
            'key_hash': self._hash_key(raw_key),
            'key_prefix': raw_key[:8],
            'scope': scope,
            'rate_limit': rate_limit,
        })
        return {
            'id': record.id,
            'name': record.name,
            'key_prefix': record.key_prefix,
            'scope': record.scope,
            'rate_limit': record.rate_limit,
            'plaintext': raw_key,
        }

    @api.model
    def authenticate(self, token):
        self.env.cr.execute(
            f"""
            SELECT id FROM {self._table}
            WHERE key_hash = %s AND active = true
            LIMIT 1
            """,
            (self._hash_key(token),),
        )
        row = self.env.cr.fetchone()
        if not row:
            return None
        try:
            with mute_logger('odoo.sql_db'), self.env.cr.savepoint():
                self.env.cr.execute(
                    f"""
                    UPDATE {self._table}
                    SET last_used = NOW() AT TIME ZONE 'UTC'
                    WHERE id = %s
                    """,
                    (row[0],),
                )
        except Exception:
            pass
        return self.sudo().browse(row[0])
