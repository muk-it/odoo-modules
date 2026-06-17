from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.safe_eval import safe_eval


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

    domain = fields.Text(
        string="Record Domain",
        help=(
            "Optional record filter applied to this model when accessed "
            "via MCP, like a record rule. When set, only records matching "
            "the domain are exposed and writable. Evaluated with 'user', "
            "'company_id', 'company_ids' and 'time' in scope, e.g. "
            "[('user_id', '=', user.id)]. Leave empty to expose all records."
        ),
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _eval_context(self):
        return {
            'user': self.env.user.with_context({}),
            'company_ids': self.env.companies.ids,
            'company_id': self.env.company.id,
        }

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
    def _get_model_domain(self, model_name):
        if not self._is_active():
            return None
        entry = self.sudo().search(
            [('model_name', '=', model_name)], limit=1,
        )
        if not entry or not entry.domain:
            return None
        return entry._eval_domain()

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

    def _eval_domain(self):
        if not self.domain:
            return []
        return safe_eval(self.domain, self._eval_context())

    # ----------------------------------------------------------
    # Constraints
    # ----------------------------------------------------------

    _sql_constraints = [
        (
            'model_unique',
            'UNIQUE(model_id)',
            "Each model can only appear once in the MCP access list.",
        ),
    ]

    @api.constrains('allow_read', 'allow_write')
    def _check_permissions(self):
        for record in self:
            if not record.allow_read and not record.allow_write:
                raise ValidationError(_(
                    "%(model)s must allow at least read or write access.",
                    model=record.model_id.name,
                ))

    @api.constrains('domain', 'model_id')
    def _check_domain(self):
        for record in self.filtered('domain'):
            try:
                domain = safe_eval(record.domain, self._eval_context())
                model = self.env[record.model_id.model].sudo()
                model._where_calc(domain)
            except Exception as error:
                raise ValidationError(_(
                    "Invalid record domain for %(model)s: %(error)s",
                    model=record.model_id.name, error=error,
                ))
