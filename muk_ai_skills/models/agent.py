from __future__ import annotations

from odoo import api, models


class AIAgent(models.Model):
    """Expose the skill tools as essential tools for every agent."""

    _inherit = 'muk_ai.agent'

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _get_default_essential_tool_names(self) -> list[str]:
        """Append the skill invocation tools to the essential tool names."""
        return super()._get_default_essential_tool_names() + [
            'invoke_skill',
            'read_resource',
        ]
