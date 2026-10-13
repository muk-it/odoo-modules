from __future__ import annotations

from odoo import models
from odoo.fields import Domain


class AISpace(models.Model):
    """Let a system space also collect the chats of the actions that name it."""

    _inherit = 'muk_ai.space'

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _parsed_domain(self) -> list:
        """Add the chats of the agent actions that file into this space."""
        return list(
            Domain.OR(
                [
                    super()._parsed_domain(),
                    [('action_server_id.agent_space_id', '=', self.id)],
                ]
            )
        )
