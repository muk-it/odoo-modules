from __future__ import annotations

from odoo import fields, models


class AIAgentSuggestion(models.Model):
    """Quick-start prompt suggestion shown for an agent."""

    _name = 'muk_ai.agent.suggestion'
    _description = 'AI Agent Suggestion'
    _order = 'sequence, id'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    agent_id = fields.Many2one(
        comodel_name='muk_ai.agent',
        string='Agent',
        required=True,
        index=True,
        ondelete='cascade',
    )

    sequence = fields.Integer(
        string='Sequence',
        default=10,
    )

    label = fields.Char(
        string='Label',
        help="Short title shown on the suggestion button (e.g. 'Explore').",
        required=True,
        translate=True,
    )

    prompt = fields.Text(
        string='Prompt',
        help='Text sent to the assistant when the user clicks this suggestion.',
        required=True,
        translate=True,
    )
