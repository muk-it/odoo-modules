from __future__ import annotations

from odoo import api, fields, models
from odoo.osv import expression


class ResPartner(models.Model):
    """Mark the contacts standing in for an AI agent."""

    _inherit = 'res.partner'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    ai_agent_ids = fields.One2many(
        comodel_name='muk_ai.agent',
        inverse_name='partner_id',
        string='AI Agents',
        help='Agents this contact stands in for in the chatter.',
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _ai_agent_partners(self) -> models.BaseModel:
        """Return the contacts of this set standing in for any agent, archived ones too."""
        agents = self.env['muk_ai.agent'].sudo().with_context(active_test=False)
        return self.browse(
            agents.search([('partner_id', 'in', self.ids)]).partner_id.ids
        )

    @api.model
    def _ai_answering_agents(self) -> models.BaseModel:
        """Return the active agents that answer a mention."""
        return self.env['muk_ai.agent'].sudo().search([('mention_enabled', '=', True)])

    def _mentionable_ai_agents(self) -> models.BaseModel:
        """Return the agents of this set of contacts that answer a mention."""
        return self._ai_answering_agents().filtered(
            lambda agent: agent.partner_id in self
        )

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    def get_ai_mention_suggestions(
        self, channel_id: int, search: str, limit: int = 8
    ) -> list[dict]:
        """Return the answering agents matching a search in a reachable conversation.

        Searched with archived contacts, which every agent contact is.
        """
        if not self.env['mail.channel'].search_count([('id', '=', channel_id)]):
            return []
        agents = self.with_context(active_test=False).search(
            expression.AND(
                [
                    expression.OR(
                        [[('name', 'ilike', search)], [('email', 'ilike', search)]]
                    ),
                    [('id', 'in', self._ai_answering_agents().partner_id.ids)],
                ]
            ),
            limit=limit,
        )
        return [
            {**partner, 'is_ai_agent': True}
            for partner in agents.mail_partner_format().values()
        ]
