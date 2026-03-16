import secrets

from odoo import fields, models, _


class MCPKeyWizard(models.TransientModel):

    _name = 'muk_mcp.key.wizard'
    _description = "MCP Key Wizard"
    _transient_max_hours = 0.1

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    name = fields.Char(
        string="Description",
        required=True,
    )

    rate_limit = fields.Integer(
        string="Rate Limit (req/min)",
        default=60,
        help="Maximum requests per minute. 0 = unlimited.",
    )

    scope_ids = fields.One2many(
        comodel_name='muk_mcp.key.wizard.scope',
        inverse_name='wizard_id',
        string="Model Scopes",
    )

    # ----------------------------------------------------------
    # Actions
    # ----------------------------------------------------------

    def action_make_key(self):
        self.ensure_one()
        raw_key = secrets.token_urlsafe(32)
        key_model = self.env['muk_mcp.key']
        key = key_model.sudo().create({
            'name': self.name,
            'user_id': self.env.uid,
            'key_hash': key_model._hash_key(raw_key),
            'key_prefix': raw_key[:8],
            'rate_limit': self.rate_limit,
        })
        if self.scope_ids:
            self.env['muk_mcp.scope'].sudo().create([
                {
                    'key_id': key.id,
                    'model_id': scope.model_id.id,
                    'perm_read': scope.perm_read,
                    'perm_write': scope.perm_write,
                    'perm_create': scope.perm_create,
                    'perm_unlink': scope.perm_unlink,
                }
                for scope in self.scope_ids
            ])
        self.unlink()
        return {
            'type': 'ir.actions.act_window',
            'name': _('MCP Key Ready'),
            'res_model': 'muk_mcp.key.show',
            'views': [(False, 'form')],
            'target': 'new',
            'context': {'default_key': raw_key},
        }


class MCPKeyWizardScope(models.TransientModel):

    _name = 'muk_mcp.key.wizard.scope'
    _description = "MCP Key Wizard Scope"
    _transient_max_hours = 0.1

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    wizard_id = fields.Many2one(
        comodel_name='muk_mcp.key.wizard',
        string="Wizard",
        required=True,
        ondelete='cascade',
    )

    model_id = fields.Many2one(
        comodel_name='ir.model',
        string="Model",
        required=True,
        ondelete='cascade',
    )

    perm_read = fields.Boolean(
        string="Read",
        default=True,
    )

    perm_write = fields.Boolean(
        string="Write",
        default=False,
    )

    perm_create = fields.Boolean(
        string="Create",
        default=False,
    )

    perm_unlink = fields.Boolean(
        string="Delete",
        default=False,
    )


class MCPKeyShow(models.AbstractModel):

    _name = 'muk_mcp.key.show'
    _description = "Show MCP Key"

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    id = fields.Id()

    key = fields.Char(
        string="API Key",
        readonly=True,
    )
