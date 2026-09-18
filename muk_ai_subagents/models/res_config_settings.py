from __future__ import annotations

from odoo import fields, models

from odoo.addons.muk_ai_subagents.tools import (
    DEFAULT_RUN_COST_LIMIT,
    DEFAULT_STALL_SECONDS,
)


class ResConfigSettings(models.TransientModel):
    """Expose the subagent run caps in the settings."""

    _inherit = 'res.config.settings'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    ai_subagent_run_cost_limit = fields.Float(
        string='Run Cost Limit',
        help=(
            'Maximum amount the subagents of one chat may spend together, in '
            'the price currency of the model. A subagent stops once the run '
            'has reached it, and no further subagent is started; the chat '
            'itself is bounded by the turn budget instead. Set 0 to '
            'disable.'
        ),
        config_parameter='muk_ai_subagents.run_cost_limit',
        default=DEFAULT_RUN_COST_LIMIT,
    )

    ai_subagent_stall_timeout = fields.Integer(
        string='Subagent Stall Timeout (s)',
        help=(
            'Seconds a running subagent may go without completing a round '
            'before the cleanup stops it and hands back what it found.'
        ),
        config_parameter='muk_ai_subagents.stall_timeout',
        default=DEFAULT_STALL_SECONDS,
    )
