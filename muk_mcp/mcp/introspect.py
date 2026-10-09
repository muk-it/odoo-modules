from odoo import api, models

from odoo.addons.muk_mcp.core.tool import mcp_tool
from odoo.addons.muk_mcp.tools.descriptions import model_field


class MCPMixin(models.AbstractModel):

    _inherit = 'muk_mcp.mixin'

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _mcp_listable_model_names(self):
        """Hook returning the listable model names, or ``None`` when unrestricted."""
        return None

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
        listable = self._mcp_listable_model_names()
        models_data = []
        for model_name, model_cls in self.env.registry.items():
            if needle and needle not in model_name.lower():
                continue
            if listable is not None and model_name not in listable:
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
            "Get the field definitions of an Odoo model: every field with its "
            "type, label, required/readonly flags and relation target (for "
            "Many2one/One2many/Many2many fields); 'selection' lists the allowed "
            "values. Pass 'fields' to get only those, with their help texts. "
            "Use this before search_read to know which fields exist."
        ),
        input_schema={
            'type': 'object',
            'properties': {
                'model': model_field(),
                'fields': {
                    'type': 'array',
                    'items': {'type': 'string'},
                    'description': (
                        'Field names to describe with their help text. Omit '
                        'for every field, without help texts.'
                    ),
                },
            },
            'required': ['model'],
        },
        category='read',
    )
    def _mcp_describe_model(self, model, fields=None):
        """Return the field definitions of a model, with help texts for named fields."""
        attributes = ['string', 'type', 'required', 'readonly', 'relation', 'selection']
        return self._resolve_model(model).fields_get(
            allfields=fields,
            attributes=[*attributes, 'help'] if fields else attributes,
        )
