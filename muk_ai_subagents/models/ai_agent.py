from __future__ import annotations

from odoo import fields, models

from odoo.addons.muk_ai_subagents.tools.constants import DELEGATION_INSTRUCTIONS


class AIAgent(models.Model):
    """Let an agent hand focused tasks to a whitelist of other agents."""

    _inherit = 'muk_ai.agent'
    _explanation = (
        'An agent may also delegate: it hands focused tasks to the agents '
        'listed as its delegates, which run them in parallel as subagents, '
        'following its delegation instructions.'
    )

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    allow_delegation = fields.Boolean(
        string='Allow Delegation',
        help=(
            'Offer the delegate tool, which hands focused tasks to the agents '
            'listed below. Each task runs as a chat of its own under that '
            'agent, with its tools and approval mode, never with more rights '
            'than this agent has.'
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
        help='The agents this one may delegate to.',
        domain=[('active', '=', True)],
    )

    delegation_instructions = fields.Text(
        string='Delegation Instructions',
        help=(
            'When this agent hands work to its delegates, in words it follows. '
            'How the delegation tools work is told to the agent apart from this.'
        ),
        default=DELEGATION_INSTRUCTIONS,
    )
