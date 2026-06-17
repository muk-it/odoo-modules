from odoo import api, models


class MCPMixin(models.AbstractModel):

    _inherit = 'muk_mcp.mixin'

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    def _mcp_list_models(self, search='', limit=100):
        result = super()._mcp_list_models(search=search, limit=limit)
        allowed = self.env[
            'muk_mcp_access.model'
        ]._get_allowed_model_names()
        if allowed is not None:
            result = [m for m in result if m['model'] in allowed]
        return result
