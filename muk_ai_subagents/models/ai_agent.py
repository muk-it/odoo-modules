from __future__ import annotations

from odoo import fields, models


class AIAgent(models.Model):
    """Let an agent hand focused tasks to a whitelist of subagent agents."""

    _inherit = 'muk_ai.agent'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    allow_delegation = fields.Boolean(
        string='Allow Delegation',
        help=(
            'Offer the delegate tool, which hands focused tasks to the '
            'agents listed below. Each task runs as a session of its own '
            'under that agent, with the tools and approval policy of that '
            'agent, narrowed to what this agent may do itself.'
        ),
        default=False,
        tracking=True,
    )

    delegate_agent_ids = fields.Many2many(
        comodel_name='muk_ai.agent',
        relation='muk_ai_agent_delegate_rel',
        column1='agent_id',
        column2='delegate_id',
        string='Delegates',
        help='Agents this one may delegate to. Nothing else is accepted.',
        domain=[('active', '=', True)],
    )
