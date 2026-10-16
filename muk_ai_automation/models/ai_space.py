from __future__ import annotations

from odoo import models
from odoo.osv import expression


class AISpace(models.Model):
    """File the chats of agent actions only where those actions send them."""

    _inherit = 'muk_ai.space'

    # ----------------------------------------------------------
    # Properties
    # ----------------------------------------------------------

    @property
    def ACTION_SPACE_XMLIDS(self) -> tuple[str, ...]:
        """Return the system spaces that collect the chats of agent actions."""
        return (
            'muk_ai_automation.space_automation',
            'muk_ai_automation.space_scheduled',
        )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _parsed_domain(self) -> list:
        """Keep action chats out of other spaces, add those filed into this one."""
        domain = super()._parsed_domain()
        action_space_ids = {
            self.env['ir.model.data']._xmlid_to_res_id(xmlid, raise_if_not_found=False)
            for xmlid in self.ACTION_SPACE_XMLIDS
        }
        if self.id not in action_space_ids:
            domain = expression.AND([domain, [('action_server_id', '=', False)]])
        return expression.OR([domain, [('action_space_id', '=', self.id)]])
