from __future__ import annotations

from odoo import fields, models


class AiAgent(models.Model):
    """Link MuK AI agents to Enterprise topics and RAG sources."""

    _inherit = 'muk_ai.agent'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    ee_topic_ids = fields.Many2many(
        comodel_name='ai.topic',
        relation='muk_ai_agent_ai_topic_rel',
        column1='muk_ai_agent_id',
        column2='ai_topic_id',
        string='EE Topics',
        help=(
            'EE ai.topic records whose tools this agent uses. '
            'Each topic bundles ir.actions.server records with '
            "use_in_ai=True; they appear in this agent's sessions as "
            'ee_action_* tools.'
        ),
    )

    ee_source_ids = fields.Many2many(
        comodel_name='ai.agent.source',
        relation='muk_ai_agent_ai_source_rel',
        column1='muk_ai_agent_id',
        column2='ai_source_id',
        string='EE RAG Sources',
        help=(
            'EE ai.agent.source records whose RAG chunks this agent '
            'uses. Top-N similar chunks are appended to the system '
            'prompt for each user message.'
        ),
    )
