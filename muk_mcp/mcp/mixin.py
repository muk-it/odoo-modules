from odoo import _, api, models
from odoo.exceptions import UserError

from odoo.addons.muk_mcp.core.tool import mcp_tool


class MCPMixin(models.AbstractModel):

    _name = 'muk_mcp.mixin'
    _description = 'MCP Tool Mixin'

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @staticmethod
    def _normalize_ids(ids):
        if ids is None:
            return []
        if isinstance(ids, int):
            return [ids]
        return list(ids)

    def _resolve_model(self, model):
        if not model or model not in self.env:
            raise UserError(_("Model %r not found", model))
        return self.env[model]

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    @mcp_tool(
        name='list_modules',
        description=(
            "List installed Odoo modules with their names, versions, and "
            "descriptions. Use 'search' to filter. This helps understand "
            "which apps and features are active in the system (e.g. is "
            "'sale' installed? is 'stock' installed?)."
        ),
        input_schema={
            'type': 'object',
            'properties': {
                'search': {
                    'type': 'string',
                    'description': 'Filter module names by substring.',
                },
                'state': {
                    'type': 'string',
                    'description': "Filter by state. Default: 'installed'.",
                    'enum': [
                        'installed', 'uninstalled',
                        'to upgrade', 'to install',
                    ],
                    'default': 'installed',
                },
            },
        },
        category='read',
    )
    def _mcp_list_modules(self, search='', state='installed'):
        domain = [('state', '=', state)]
        if search:
            domain.append(('name', 'ilike', search))
        modules = self.env['ir.module.module'].sudo().search_read(
            domain,
            fields=['name', 'shortdesc', 'state', 'installed_version'],
            order='name asc',
        )
        return [
            {
                'name': m['name'],
                'label': m['shortdesc'],
                'version': m['installed_version'] or '',
                'state': m['state'],
            }
            for m in modules
        ]
