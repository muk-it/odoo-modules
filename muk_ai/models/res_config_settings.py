from __future__ import annotations

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    """Expose AI provider, agent, and runtime limits in the settings."""

    _inherit = 'res.config.settings'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    ai_provider_id = fields.Many2one(
        related='company_id.default_ai_provider_id',
        readonly=False,
    )

    ai_agent_id = fields.Many2one(
        related='company_id.default_ai_agent_id',
        readonly=False,
    )

    ai_max_iterations = fields.Integer(
        string='Max Iterations',
        help=(
            'Maximum number of LLM rounds per worker slice. The model is '
            'warned shortly before the limit so it can wrap up.'
        ),
        config_parameter='muk_ai.max_iterations',
        default=20,
    )

    ai_slice_wallclock_seconds = fields.Integer(
        string='Slice Wallclock (s)',
        help=(
            'Maximum seconds a single worker slice may run before the turn '
            'is checkpointed and resumed by a fresh worker. Capped by the '
            'cron time limit.'
        ),
        config_parameter='muk_ai.slice_wallclock_seconds',
        default=600,
    )

    ai_turn_wallclock_seconds = fields.Integer(
        string='Turn Wallclock (s)',
        help=(
            'Maximum total seconds a single user turn may run across all '
            'worker slices before it stops with an error.'
        ),
        config_parameter='muk_ai.turn_wallclock_seconds',
        default=3600,
    )

    ai_turn_cost_limit = fields.Float(
        string='Turn Cost Limit',
        help=(
            'Maximum amount a single user turn may spend, in the price '
            'currency of the model. The model is warned at 80% and the '
            'turn stops with an error when the limit is reached. Set 0 '
            'to disable.'
        ),
        config_parameter='muk_ai.turn_cost_limit',
    )
