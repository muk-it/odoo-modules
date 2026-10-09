from __future__ import annotations

from odoo import api, fields, models
from odoo.osv import expression

from odoo.addons.mail.tools.discuss import Store


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
    # ORM
    # ----------------------------------------------------------

    @api.readonly
    @api.model
    def get_mention_suggestions_from_channel(
        self, channel_id: int, search: str, limit: int = 8
    ) -> dict | list:
        """Offer the answering agents of a Discuss conversation next to its members.

        Searched with archived contacts, which every agent contact is.
        """
        result = super().get_mention_suggestions_from_channel(channel_id, search, limit)
        if not result:
            return result
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
        store = Store(agents)
        for agent in agents:
            store.add(agent, {'is_ai_agent': True})
        for model_name, records in store.get_result().items():
            result.setdefault(model_name, []).extend(records)
        return result
