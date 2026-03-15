import hashlib
import time

from odoo import api, fields, models

_rate_limit_store = {}


class MCPKey(models.Model):

    _name = 'muk_mcp.key'
    _description = "MCP API Key"
    _order = 'name'

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
        index=True,
        ondelete='cascade',
        default=lambda self: self.env.user,
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

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @staticmethod
    def _hash_key(key):
        return hashlib.sha256(key.encode()).hexdigest()

    def _check_rate_limit(self):
        self.ensure_one()
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
        self.ensure_one()
        if not self.scope_ids:
            return True
        scope = self.scope_ids.filtered(
            lambda s: s.model_name == model_name
        )
        if not scope:
            return False
        perm_map = {
            'read': 'perm_read',
            'write': 'perm_write',
            'create': 'perm_create',
            'unlink': 'perm_unlink',
        }
        field_name = perm_map.get(operation)
        if not field_name:
            return False
        return scope[0][field_name]

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    def authenticate(self, token):
        key_hash = self._hash_key(token)
        key = self.sudo().search([
            ('key_hash', '=', key_hash),
            ('active', '=', True),
        ], limit=1)
        if not key:
            return None
        key.sudo().write({'last_used': fields.Datetime.now()})
        return key
