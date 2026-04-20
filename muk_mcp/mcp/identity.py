from odoo import api, models

from odoo.addons.muk_mcp.core.tool import mcp_tool


class MCPMixin(models.AbstractModel):

    _inherit = 'muk_mcp.mixin'

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    @mcp_tool(
        name='whoami',
        description=(
            'Get information about the current authenticated user: their '
            'name, login, language, timezone, company, currency, country, '
            'and security groups. Use this at the start of a conversation '
            'to understand who you are acting as, what permissions you '
            'have, and what company context you are in.'
        ),
        input_schema={
            'type': 'object',
            'properties': {},
        },
        category='read',
    )
    def _mcp_whoami(self):
        user = self.env.user
        company = self.env.company
        return {
            'uid': user.id,
            'login': user.login,
            'name': user.name,
            'lang': user.lang,
            'tz': user.tz or '',
            'company_id': company.id,
            'company_name': company.name,
            'currency': company.currency_id.name,
            'country': company.country_id.name or '',
            'groups': [
                g.full_name for g in user.group_ids.sorted('full_name')
            ],
        }

    @api.model
    @mcp_tool(
        name='get_access_rights',
        description=(
            "Check the current user's access rights on a model (read, "
            "write, create, unlink) and list all access control rules "
            "defined for it. Use this to understand why an operation "
            "might be forbidden or to verify permissions before "
            "attempting a write operation."
        ),
        input_schema={
            'type': 'object',
            'properties': {
                'model': {
                    'type': 'string',
                    'description': (
                        "Technical model name (e.g. 'sale.order')."
                    ),
                },
            },
            'required': ['model'],
        },
        category='read',
    )
    def _mcp_get_access_rights(self, model):
        target = self._resolve_model(model)
        rights = {}
        for op in ('read', 'write', 'create', 'unlink'):
            try:
                target.check_access(op)
                rights[op] = True
            except Exception:
                rights[op] = False
        rules = self.env['ir.model.access'].sudo().search_read(
            [('model_id.model', '=', model)],
            fields=[
                'name', 'group_id', 'perm_read', 'perm_write',
                'perm_create', 'perm_unlink',
            ],
        )
        return {
            'model': model,
            'current_user_rights': rights,
            'access_rules': rules,
        }
