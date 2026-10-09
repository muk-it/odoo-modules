from __future__ import annotations

from odoo import api, fields, models
from odoo.fields import Domain

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

    def _store_mention_fields(self, res: Store.FieldList) -> None:
        """Tell the client which suggested contacts are agents."""
        super()._store_mention_fields(res)
        agent_ids = set(self._ai_answering_agents().partner_id.ids)
        res.attr('is_ai_agent', lambda partner: partner.id in agent_ids)

    @api.readonly
    @api.model
    def get_mention_suggestions_from_channel(
        self, channel_id: int, search: str, limit: int = 8
    ) -> Store | list:
        """Offer the answering agents of a Discuss conversation next to its members.

        Searched with archived contacts, which every agent contact is.
        """
        store = super().get_mention_suggestions_from_channel(channel_id, search, limit)
        if not store:
            return store
        term = Domain('name', 'ilike', search) | Domain('email', 'ilike', search)
        agents = self.with_context(active_test=False).search(
            term & Domain('id', 'in', self._ai_answering_agents().partner_id.ids),
            limit=limit,
        )
        store.add(
            agents,
            lambda res: (
                res.from_method('_store_partner_fields'),
                res.from_method('_store_mention_fields'),
            ),
        )
        return store
