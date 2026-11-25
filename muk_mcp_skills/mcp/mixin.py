from __future__ import annotations

from typing import Any

from odoo import api, models

from odoo.addons.muk_mcp.tools.content import make_resource_entry
from odoo.addons.muk_mcp_skills.tools.constants import SKILL_SCHEME


class MCPMixin(models.AbstractModel):
    """Serve the files of the skills through ``resources/read``."""

    _inherit = 'muk_mcp.mixin'

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _dispatch_resources_read(self, uri: str) -> dict[str, Any] | None:
        """Read a ``skill://`` file; any other URI goes to the base resolvers."""
        if not uri.startswith(SKILL_SCHEME):
            return super()._dispatch_resources_read(uri)
        file = self.env['muk_mcp_skills.skill']._find(uri)._files().get(uri)
        return file and make_resource_entry(uri, *file)
