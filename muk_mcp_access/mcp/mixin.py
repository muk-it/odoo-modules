from odoo import _, api, models
from odoo.exceptions import AccessError
from odoo.http import request
from odoo.osv import expression

from odoo.addons.muk_mcp.tools.parser import coerce_json_value, normalize_ids


class MCPMixin(models.AbstractModel):

    _inherit = 'muk_mcp.mixin'

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _resolve_model(self, model):
        result = super()._resolve_model(model)
        category = (
            getattr(request, '_mcp_tool_category', None)
            if request else None
        ) or 'read'
        if not self.env['muk_mcp_access.model']._is_model_allowed(
            model, category,
        ):
            raise AccessError(_(
                "Model %(model)r is not accessible via MCP.",
                model=model,
            ))
        return result

    @api.model
    def _mcp_record_domain(self, model):
        return self.env['muk_mcp_access.model']._get_model_domain(model)

    @api.model
    def _mcp_apply_domain(self, model, domain):
        extra = self._mcp_record_domain(model)
        if extra is None:
            return domain
        base = coerce_json_value(domain) or []
        return expression.AND([base, extra])

    @api.model
    def _mcp_assert_records_allowed(self, model, ids):
        extra = self._mcp_record_domain(model)
        ids = normalize_ids(ids)
        if extra is None or not ids:
            return
        allowed = set(self.env[model].with_context(active_test=False).search(
            expression.AND([[('id', 'in', ids)], extra]),
        ).ids)
        forbidden = [rid for rid in ids if rid not in allowed]
        if forbidden:
            raise AccessError(_(
                "Records %(ids)s of %(model)r are not accessible via MCP.",
                ids=forbidden, model=model,
            ))

    @api.model
    def _resolve_resource_record_field(self, model, record_id, field):
        self._mcp_assert_records_allowed(model, [record_id])
        return super()._resolve_resource_record_field(
            model, record_id, field,
        )
