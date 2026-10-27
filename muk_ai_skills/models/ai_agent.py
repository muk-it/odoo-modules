from __future__ import annotations

from odoo import models


class AIAgent(models.Model):
    """Let every agent invoke the skills scoped to it, whatever its tool filter."""

    _inherit = 'muk_ai.agent'

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _admits_tool(self, name: str) -> bool:
        """Admit the skill tool: a skill's own scope decides who may run it."""
        return name == 'invoke_skill' or super()._admits_tool(name)
