from __future__ import annotations

from odoo import api, fields, models


class AIAgent(models.Model):
    """Back agents with a contact so they can be mentioned in a conversation."""

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

    def _provision_partners(self) -> None:
        """Give every agent an archived, address-less contact named after it.

        Archived keeps it out of the address book and every contact picker;
        the mention suggestions of a conversation opt back in.
        """
        partners = self.env['res.partner'].sudo()
        for agent in self:
            values = {'name': agent.name, 'email': False, 'active': False}
            if agent.partner_id:
                agent.partner_id.sudo().write(values)
            else:
                agent.partner_id = partners.create(values)

    # ----------------------------------------------------------
    # ORM
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
