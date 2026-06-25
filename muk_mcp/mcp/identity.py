from __future__ import annotations

from typing import Any

from odoo import api, models
from odoo.exceptions import AccessError

from odoo.addons.muk_mcp.core.tool import mcp_tool
from odoo.addons.muk_mcp.tools.descriptions import model_field


class MCPMixin(models.AbstractModel):
    """Add the ``whoami`` and ``get_access_rights`` MCP tools."""

    _inherit = 'muk_mcp.mixin'

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    @mcp_tool(
        name='whoami',
        description=(
            'Get information about the current authenticated user: their '
            'name, login, language, timezone, active company, currency, '
            'country, and security groups. Also returns the full list of '
            'companies the user can access and the currently allowed '
            'company ids. Use this at the start of a conversation to '
            'understand who you are acting as, what permissions you have, '
            'and what company context you are in. To target a specific '
            'company on a subsequent tool call, pass '
            'context={"allowed_company_ids": [id]} in the tool arguments.'
        ),
        input_schema={
            'type': 'object',
            'properties': {},
        },
        category='read',
    )
    def _mcp_whoami(self) -> dict[str, Any]:
        """Return identity and context for the authenticated user.

        Reports the user, their active company and the accessible companies
        (sorted by sequence) plus their security groups, so a client knows who
        it is acting as and in which company context.
        """
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
            'companies': [
                {
                    'id': c.id,
                    'name': c.name,
                    'currency': c.currency_id.name,
                    'country': c.country_id.name or '',
                }
                for c in user.company_ids.sorted('sequence')
            ],
            'groups': [g.full_name for g in user.group_ids.sorted('full_name')],
        }

    @api.model
    @mcp_tool(
        name='get_access_rights',
        description=(
            "Check the current user's access rights on a model (read, "
            'write, create, unlink) and list all access control rules '
            'defined for it. Use this to understand why an operation '
            'might be forbidden or to verify permissions before '
            'attempting a write operation.'
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
    def _mcp_get_access_rights(self, model: str) -> dict[str, Any]:
        """Report the user's CRUD rights and ACL rules for a model.

        Probes ``read``/``write``/``create``/``unlink`` via
        :meth:`check_access` and returns each as a boolean alongside the
        ``ir.model.access`` rules defined for the model.
        """
        target = self._resolve_model(model)
        rights = {}
        for op in ('read', 'write', 'create', 'unlink'):
            try:
                target.check_access(op)
                rights[op] = True
            except AccessError:
                rights[op] = False
        rules = (
            self.env['ir.model.access']
            .sudo()
            .search_read(
                [('model_id.model', '=', model)],
                fields=[
                    'name',
                    'group_id',
                    'perm_read',
                    'perm_write',
                    'perm_create',
                    'perm_unlink',
                ],
            )
        )
        return {
            'model': model,
            'current_user_rights': rights,
            'access_rules': rules,
        }
