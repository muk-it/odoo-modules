from __future__ import annotations

from odoo import api, models


class AISession(models.Model):
    """Load the decide tool upfront whenever a decision model can answer."""

    _inherit = 'muk_ai.session'

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _eager_tool_name_registry(self) -> set[str]:
        """Register the decide tool as loaded by the session, not chosen on the agent."""
        return super()._eager_tool_name_registry() | {'decide'}

    def _eager_tool_names(self) -> set[str]:
        """Load the decide tool when a provider offers a decision model."""
        names = super()._eager_tool_names()
        if self.env['muk_ai.decision']._candidates(None):
            names.add('decide')
        return names
