from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class MCPAccessModel(models.Model):

    _name = 'muk_mcp_access.model'
    _description = "MCP Model Access"
    _rec_name = 'model_name'
    _order = 'model_name'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    model_id = fields.Many2one(
        comodel_name='ir.model',
        string="Model",
        required=True,
        index=True,
        ondelete='cascade',
    )

    model_name = fields.Char(
        related='model_id.model',
        string="Technical Name",
        store=True,
        index=True,
    )

    active = fields.Boolean(
        string="Active",
        default=True,
    )

    allow_read = fields.Boolean(
        string="Read",
        default=True,
    )

    allow_write = fields.Boolean(
        string="Write",
        default=False,
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _is_active(self):
        return bool(self.sudo().search_count([]))

    @api.model
    def _is_model_allowed(self, model_name, category='read'):
        if not self._is_active():
            return True
        entry = self.sudo().search(
            [('model_name', '=', model_name)], limit=1,
        )
        if not entry:
            return False
        if category == 'write':
            return entry.allow_write
        return entry.allow_read

    @api.model
    def _get_allowed_model_names(self, category=None):
        if not self._is_active():
            return None
        domain = []
        if category == 'read':
            domain.append(('allow_read', '=', True))
        elif category == 'write':
            domain.append(('allow_write', '=', True))
        return set(self.sudo().search(domain).mapped('model_name'))

    # ----------------------------------------------------------
    # Constraints
    # ----------------------------------------------------------

    _model_unique = models.Constraint(
        'UNIQUE(model_id)',
        "Each model can only appear once in the MCP access list.",
    )

    @api.constrains('allow_read', 'allow_write')
    def _check_permissions(self):
        for record in self:
            if not record.allow_read and not record.allow_write:
                raise ValidationError(_(
                    "%(model)s must allow at least read or write access.",
                    model=record.model_id.name,
                ))
