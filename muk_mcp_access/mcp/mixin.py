from odoo import _, api, models
from odoo.exceptions import AccessError
from odoo.http import request


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
