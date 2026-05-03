from odoo import api, models

from odoo.addons.muk_mcp.core.tool import mcp_tool
from odoo.addons.muk_mcp.tools.descriptions import model_field


class MCPMixin(models.AbstractModel):

    _inherit = 'muk_mcp.mixin'

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    @mcp_tool(
        name='list_models',
        description=(
            "List available Odoo models with their technical names and "
            "human-readable descriptions. Use 'search' to filter by "
            "substring (e.g. 'sale', 'account', 'stock'). This is the "
            "starting point to discover what data exists in the system "
            "before querying it. Common models: res.partner (contacts), "
            "sale.order (sales), account.move (invoices), stock.picking "
            "(deliveries), project.task (tasks), hr.employee (employees)."
        ),
        input_schema={
            'type': 'object',
            'properties': {
                'search': {
                    'type': 'string',
                    'description': (
                        "Filter model names by substring (case-insensitive). "
                        "Examples: 'sale', 'partner', 'account', 'stock', "
                        "'project'."
                    ),
                },
                'limit': {
                    'type': 'integer',
                    'description': 'Maximum number of models to return.',
                    'default': 100,
                },
            },
        },
        category='read',
    )
    def _mcp_list_models(self, search='', limit=100):
        needle = (search or '').lower()
        models_data = []
        for model_name, model_cls in self.env.registry.items():
            if needle and needle not in model_name.lower():
                continue
            description = getattr(model_cls, '_description', None) or model_name
            models_data.append({
                'model': model_name,
                'description': description,
            })
        models_data.sort(key=lambda m: m['model'])
        return models_data[:limit]

    @api.model
    @mcp_tool(
        name='describe_model',
        description=(
            "Get the complete field definitions for an Odoo model. Returns "
            "every field with its type, label, help text, required/readonly "
            "flags, and relation target (for Many2one/One2many/Many2many "
            "fields). Use this before search_read to know which fields "
            "exist and what types they are. The 'selection' attribute "
            "shows allowed values for Selection fields."
        ),
        input_schema={
            'type': 'object',
            'properties': {
                'model': model_field(),
            },
            'required': ['model'],
        },
        category='read',
    )
    def _mcp_describe_model(self, model):
        return self._resolve_model(model).fields_get(
            attributes=[
                'string', 'type', 'help', 'required',
                'readonly', 'relation', 'selection',
            ],
        )
