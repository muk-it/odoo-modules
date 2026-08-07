from __future__ import annotations

from odoo import api, fields, models


class AIAgent(models.Model):
    """Back agents with a partner so they can be mentioned in a conversation."""

    _inherit = 'muk_ai.agent'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    partner_id = fields.Many2one(
        comodel_name='res.partner',
        string='Agent Contact',
        help=(
            'Contact standing in for this agent in the chatter. It carries no '
            'email address, so mentioning the agent never mails anybody.'
        ),
        copy=False,
        ondelete='restrict',
    )

    mention_enabled = fields.Boolean(
        string='Answer Mentions',
        help=(
            'Let users summon this agent from a Discuss channel or a direct '
            'chat by mentioning it, and post its answer back there.'
        ),
        default=True,
        tracking=True,
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _partner_values(self) -> dict:
        """Return the values the agent's stand-in contact is kept at.

        The contact is archived on purpose. It exists only so the agent can
        author a note and carry a mention chip — it is not a person anybody
        should find in the address book, and archiving keeps it out of the
        Contacts app and every ``res.partner`` picker at once, since neither
        applies a domain we could hook. Mention suggestions opt back in.
        """
        return {
            'name': self.name,
            'email': False,
            'active': False,
        }

    def _provision_partners(self) -> None:
        """Give every agent in this set a stand-in contact, creating it once."""
        partners = self.env['res.partner'].sudo()
        for agent in self:
            if agent.partner_id:
                agent.partner_id.write(agent._partner_values())
                continue
            agent.partner_id = partners.create(agent._partner_values())

    # ----------------------------------------------------------
    # ORM methods
    # ----------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list: list[dict]) -> AIAgent:
        """Create agents along with the contact standing in for them."""
        agents = super().create(vals_list)
        agents._provision_partners()
        return agents

    def write(self, vals: dict) -> bool:
        """Keep the stand-in contact named after the agent."""
        result = super().write(vals)
        if 'name' in vals:
            self.filtered('partner_id')._provision_partners()
        return result
