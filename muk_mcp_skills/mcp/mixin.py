from __future__ import annotations

from odoo import api, models

from odoo.addons.muk_mcp_skills.tools.constants import SKILL_SCHEME


class MCPMixin(models.AbstractModel):
    """Resolve the files of the skills next to the base resources."""

    _inherit = 'muk_mcp.mixin'

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _resolve_resource_uri(self, uri: str) -> tuple[str, bytes, str]:
        """Load a ``skill://`` file; any other or unknown URI goes to the base."""
        if uri.startswith(SKILL_SCHEME):
            file = self.env['muk_mcp_skills.skill']._find(uri)._files().get(uri)
            if file:
                return file
        return super()._resolve_resource_uri(uri)
