from __future__ import annotations

from odoo import api, fields, models

from odoo.addons.muk_ai.tools import SEARCH_BACKENDS


class ResConfigSettings(models.TransientModel):
    """Expose AI provider, agent, web search and runtime limits in the settings."""

    _inherit = 'res.config.settings'

    # ----------------------------------------------------------
    # Selections
    # ----------------------------------------------------------

    def _selection_ai_search_backend(self) -> list[tuple[str, str]]:
        """Return the registered web search backends as selection values."""
        return [(cls.code, cls.label) for cls in SEARCH_BACKENDS.values()]

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

    ai_search_backend = fields.Selection(
        selection=lambda self: self._selection_ai_search_backend(),
        string='Web Search Backend',
        help=(
            'Search API the web_search tool queries. Once set, every agent '
            'with web search enabled searches through it instead of the '
            "provider's built-in connector, on every provider. Country and "
            'language follow the company and the user.'
        ),
        config_parameter='muk_ai.search_backend',
    )

    ai_search_api_key = fields.Char(
        string='Web Search API Key',
        config_parameter='muk_ai.search_api_key',
    )

    ai_search_needs_key = fields.Boolean(
        compute='_compute_ai_search_requirements',
        string='Backend Needs a Key',
    )

    ai_search_needs_url = fields.Boolean(
        compute='_compute_ai_search_requirements',
        string='Backend Needs a URL',
    )

    ai_search_url = fields.Char(
        string='Web Search URL',
        help=(
            'Base URL of the self-hosted instance, e.g. http://searxng:8080. '
            'Only a self-hosted backend is queried here; the vendor APIs '
            'answer at their own endpoint and ignore this value.'
        ),
        config_parameter='muk_ai.search_url',
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

    ai_session_retention_enabled = fields.Boolean(
        string='Chat Retention',
        help=(
            'Let the scheduled cleanup delete finished chats once they are '
            'old enough. A chat that is still running is never touched.'
        ),
        config_parameter='muk_ai.session_retention_enabled',
    )

    ai_session_retention_days = fields.Integer(
        string='Retention Days',
        help='Days a finished chat is kept before the cleanup deletes it.',
        config_parameter='muk_ai.session_retention_days',
        default=90,
    )

    ai_client_action_timeout = fields.Integer(
        string='Client Action Timeout (s)',
        help=(
            'Seconds a chat waits for the browser to carry out an action it '
            'asked for before the cleanup answers for it and lets the turn '
            'go on. Zero waits for good.'
        ),
        config_parameter='muk_ai.client_action_timeout',
        default=600,
    )

    # ----------------------------------------------------------
    # Compute
    # ----------------------------------------------------------

    @api.depends('ai_search_backend')
    def _compute_ai_search_requirements(self) -> None:
        """Tell the form which credentials the chosen backend actually takes."""
        for record in self:
            backend = SEARCH_BACKENDS.get(record.ai_search_backend)
            record.ai_search_needs_key = bool(backend and backend.needs_key)
            record.ai_search_needs_url = bool(backend and backend.needs_url)
