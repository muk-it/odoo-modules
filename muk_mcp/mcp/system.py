from __future__ import annotations

from typing import Any

from odoo import api, models, release

from odoo.addons.muk_mcp.core.tool import mcp_tool


class MCPMixin(models.AbstractModel):
    """Add the ``system_info``, ``list_modules`` and ``list_languages`` MCP tools."""

    _inherit = 'muk_mcp.mixin'

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _system_info(self) -> dict[str, Any]:
        """Return version, edition, and deployment facts about this Odoo server.

        Single source of truth for server-level identity so any client (or a
        prompt runtime block) reports the same version and edition. Edition is
        read from the release version marker — the same signal Odoo's own web
        client uses (``version_info[-1] == 'e'``) — not from a module lookup.
        """
        return {
            'product': release.product_name,
            'version': release.version,
            'series': release.serie,
            'edition': 'enterprise' if release.version_info[-1] == 'e' else 'community',
            'database': self.env.cr.dbname,
            'base_url': self.env['ir.config_parameter'].sudo().get_param('web.base.url')
            or '',
        }

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    @mcp_tool(
        name='system_info',
        description=(
            'Get identity facts about the Odoo server itself: product name, '
            'version, series, edition (community or enterprise), database '
            'name, and base URL. Use this to learn which Odoo you are '
            'connected to and what edition-gated features may be available. '
            'For the current user and company context use whoami; for the '
            'installed module inventory use list_modules; for installed '
            'languages use list_languages.'
        ),
        input_schema={
            'type': 'object',
            'properties': {},
        },
        category='read',
    )
    def _mcp_system_info(self) -> dict[str, Any]:
        """Report server version, edition, and deployment facts."""
        return self._system_info()

    @api.model
    @mcp_tool(
        name='list_modules',
        description=(
            'List installed Odoo modules with their names, versions, and '
            'descriptions. Use "search" to filter. This helps understand '
            'which apps and features are active in the system (e.g. is '
            '"sale" installed? is "stock" installed?).'
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
                        'installed',
                        'uninstalled',
                        'to upgrade',
                        'to install',
                    ],
                    'default': 'installed',
                },
            },
        },
        category='read',
    )
    def _mcp_list_modules(
        self,
        search: str = '',
        state: str = 'installed',
    ) -> list[dict[str, Any]]:
        """List modules in a given state, optionally filtered by name.

        Returns name, label, installed version and state for each matching
        ``ir.module.module`` record, ordered by name.
        """
        domain = [('state', '=', state)]
        if search:
            domain.append(('name', 'ilike', search))
        modules = (
            self.env['ir.module.module']
            .sudo()
            .search_read(
                domain,
                fields=['name', 'shortdesc', 'state', 'installed_version'],
                order='name asc',
            )
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

    @api.model
    @mcp_tool(
        name='list_languages',
        description=(
            'List the languages installed on this Odoo server, each with '
            'its code and display name. Use this to know which translations '
            'and locale-specific formatting the system supports.'
        ),
        input_schema={
            'type': 'object',
            'properties': {},
        },
        category='read',
    )
    def _mcp_list_languages(self) -> list[dict[str, str]]:
        """List installed (active) languages with their code and display name."""
        return [
            {'code': code, 'name': name}
            for code, name in self.env['res.lang'].get_installed()
        ]
