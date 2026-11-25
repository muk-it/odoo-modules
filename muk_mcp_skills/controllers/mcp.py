from __future__ import annotations

import base64
from collections.abc import Callable
from typing import Any

from odoo.http import request

from odoo.addons.muk_mcp.controllers.mcp import MCPController
from odoo.addons.muk_mcp.tools import version
from odoo.addons.muk_mcp.tools.content import is_textual_mimetype
from odoo.addons.muk_mcp.tools.exception import MCPResourceNotFound
from odoo.addons.muk_mcp.tools.version import ProtocolProfile
from odoo.addons.muk_mcp_skills.tools.constants import EXTENSION_KEY, SKILL_SCHEME


class MCPController(MCPController):
    """Serve the Skills extension: its capability, ``skills/list`` and ``skills/get``."""

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _get_handlers(self, profile: ProtocolProfile) -> dict[str, Callable]:
        """Add the skill methods, which only the stateless revision defines."""
        handlers = super()._get_handlers(profile)
        if profile.stateless:
            handlers['skills/list'] = self._handle_skills_list
            handlers['skills/get'] = self._handle_skills_get
        return handlers

    def _get_capabilities(
        self, params: dict[str, Any], profile: ProtocolProfile
    ) -> dict[str, Any]:
        """Advertise the Skills extension on the stateless revision."""
        capabilities = super()._get_capabilities(params, profile)
        if profile.stateless:
            capabilities.setdefault('extensions', {})[EXTENSION_KEY] = {}
            capabilities.setdefault('resources', {})
        return capabilities

    def _handle_skills_list(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle ``skills/list``: return an entry for every skill of the user."""
        skills = request.env['muk_mcp_skills.skill'].search([])
        return {
            'skills': [skill._entry() for skill in skills],
            **version.MCP_CACHE_HINTS['tools/list'],
        }

    def _handle_skills_get(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle ``skills/get``: return the entry of the skill at ``uri``."""
        uri = params.get('uri') or ''
        skill = request.env['muk_mcp_skills.skill']._find(uri)
        if not skill or uri != skill._uri():
            raise MCPResourceNotFound
        return {'skill': skill._entry(), **version.MCP_CACHE_HINTS['tools/list']}

    def _handle_resources_read(self, params: dict[str, Any]) -> dict[str, Any]:
        """Read a ``skill://`` file; any other URI goes to the base."""
        uri = params.get('uri') or ''
        if not uri.startswith(SKILL_SCHEME):
            return super()._handle_resources_read(params)
        file = request.env['muk_mcp_skills.skill']._find(uri)._files().get(uri)
        if not file:
            raise MCPResourceNotFound
        mimetype, raw, name = file
        content = {'uri': uri, 'mimeType': mimetype, 'name': name}
        if is_textual_mimetype(mimetype):
            try:
                return {'contents': [{**content, 'text': raw.decode()}]}
            except UnicodeDecodeError:
                pass
        blob = base64.b64encode(raw).decode('ascii')
        return {'contents': [{**content, 'blob': blob}]}
