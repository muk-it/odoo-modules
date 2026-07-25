from __future__ import annotations

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.fields import Domain
from odoo.tools.safe_eval import safe_eval


class MCPAccessModel(models.Model):
    """Whitelist entry declaring how a model may be reached through MCP."""

    _name = 'muk_mcp_access.model'
    _description = 'MCP Model Access'
    _rec_name = 'model_name'
    _order = 'model_name'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    model_id = fields.Many2one(
        comodel_name='ir.model',
        string='Model',
        required=True,
        index=True,
        ondelete='cascade',
    )

    model_name = fields.Char(
        related='model_id.model',
        string='Technical Name',
        store=True,
        index=True,
    )

    active = fields.Boolean(
        string='Active',
        default=True,
    )

    allow_read = fields.Boolean(
        string='Read',
        default=True,
    )

    allow_write = fields.Boolean(
        string='Write',
        default=False,
    )

    domain = fields.Text(
        string='Record Domain',
        help=(
            'Optional record filter applied to this model when accessed '
            'via MCP, like a record rule. When set, only records matching '
            'the domain are exposed and writable. Evaluated with "user", '
            '"company_id", "company_ids" and "time" in scope, e.g. '
            '[("user_id", "=", user.id)]. Leave empty to expose all records.'
        ),
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _eval_context(self) -> dict:
        """Build the safe-eval namespace used to evaluate record domains."""
        return {
            'user': self.env.user.with_context({}),
            'company_ids': self.env.companies.ids,
            'company_id': self.env.company.id,
        }

    def _entries(self) -> MCPAccessModel:
        """Return allowlist entries as superuser, ignoring caller ``active_test``.

        Access-control lookups must never honour a caller-supplied
        ``active_test=False`` context, which would otherwise resurrect
        archived (disabled) entries and bypass the allowlist.
        """
        return self.sudo().with_context(active_test=True)

    @api.model
    def _is_active(self) -> bool:
        """Return whether any allowlist entry exists (whitelisting is enabled)."""
        return bool(self._entries().search_count([]))

    @api.model
    def _is_model_allowed(self, model_name: str, category: str = 'read') -> bool:
        """Return whether a model is reachable via MCP for the given tool category."""
        if not self._is_active():
            return True
        entry = self._entries().search(
            [('model_name', '=', model_name)],
            limit=1,
        )
        if not entry:
            return False
        if category == 'write':
            return entry.allow_write
        return entry.allow_read

    @api.model
    def _get_model_domain(self, model_name: str) -> list | None:
        """Return the evaluated record domain for a model, or ``None`` when unrestricted."""
        if not self._is_active():
            return None
        entry = self._entries().search(
            [('model_name', '=', model_name)],
            limit=1,
        )
        if not entry or not entry.domain:
            return None
        return entry._eval_domain()

    @api.model
    def _get_allowed_model_names(self, category: str | None = None) -> set | None:
        """Return the set of allowed model names for a category, or ``None`` when unrestricted."""
        if not self._is_active():
            return None
        domain = []
        if category == 'read':
            domain.append(('allow_read', '=', True))
        elif category == 'write':
            domain.append(('allow_write', '=', True))
        return set(self._entries().search(domain).mapped('model_name'))

    def _eval_domain(self) -> list:
        """Safe-evaluate this entry's record domain text into a domain list."""
        if not self.domain:
            return []
        return safe_eval(self.domain, self._eval_context())

    # ----------------------------------------------------------
    # Constraints
    # ----------------------------------------------------------

    _model_unique = models.Constraint(
        'UNIQUE(model_id)',
        'Each model can only appear once in the MCP access list.',
    )

    @api.constrains('allow_read', 'allow_write')
    def _check_permissions(self) -> None:
        """Ensure each entry grants at least read or write access.

        :raise ValidationError: when neither read nor write access is granted.
        """
        for record in self:
            if not record.allow_read and not record.allow_write:
                raise ValidationError(
                    _(
                        '%(model)s must allow at least read or write access.',
                        model=record.model_id.name,
                    )
                )

    @api.constrains('domain', 'model_id')
    def _check_domain(self) -> None:
        """Validate that each record domain parses against its target model.

        :raise ValidationError: when the domain text is invalid for the model.
        """
        for record in self.filtered('domain'):
            try:
                domain = safe_eval(record.domain, self._eval_context())
                model = self.env[record.model_id.model].sudo()
                Domain(domain).validate(model)
            except Exception as error:
                raise ValidationError(
                    _(
                        'Invalid record domain for %(model)s: %(error)s',
                        model=record.model_id.name,
                        error=error,
                    )
                ) from error
