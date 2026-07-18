from __future__ import annotations

from odoo import _, api, fields, models, release

from odoo.addons.muk_ai.tools import (
    DEFAULT_CONTEXT_WINDOW,
    REASONING_EFFORT_SELECTION,
)
from odoo.addons.muk_mcp.core.tool import get_tool_index


class AIAgent(models.Model):
    """Configured AI agent: prompt, model, tools, and approval policy."""

    _name = 'muk_ai.agent'
    _description = 'AI Agent'
    _inherit = [
        'image.mixin',
        'mail.thread',
        'mail.activity.mixin',
        'muk_ai.revision.mixin',
        'muk_ai.prompt.mixin',
    ]
    _order = 'sequence, name'

    @api.model
    def _get_prompt_fields(self) -> list[str]:
        """Return the prompt fields tracked for revision history."""
        return ['system_prompt']

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    name = fields.Char(
        string='Name',
        required=True,
        translate=True,
        tracking=True,
    )

    active = fields.Boolean(
        string='Active',
        default=True,
        tracking=True,
    )

    sequence = fields.Integer(
        string='Sequence',
        default=10,
    )

    description = fields.Text(
        string='Description',
        translate=True,
    )

    system_prompt = fields.Text(
        string='System Prompt',
        translate=True,
    )

    model_id = fields.Many2one(
        comodel_name='muk_ai.model',
        string='Model',
        help=(
            'Model used by this agent. Leave empty to use the company default model.'
        ),
        ondelete='set null',
        tracking=True,
    )

    supports_web_search = fields.Boolean(
        compute='_compute_provider_capabilities',
        string='Supports Web Search',
    )

    supports_image_generation = fields.Boolean(
        compute='_compute_provider_capabilities',
        string='Supports Image Generation',
    )

    supports_code_interpreter = fields.Boolean(
        compute='_compute_provider_capabilities',
        string='Supports Code Interpreter',
    )

    enable_web_search = fields.Boolean(
        compute='_compute_enable_web_search',
        string='Enable Web Search',
        help="Let the LLM use the provider's native web search tool.",
        readonly=False,
        store=True,
        tracking=True,
    )

    enable_image_generation = fields.Boolean(
        compute='_compute_enable_image_generation',
        string='Enable Image Generation',
        help="Let the LLM generate images via the provider's native tool.",
        readonly=False,
        store=True,
        tracking=True,
    )

    enable_code_interpreter = fields.Boolean(
        compute='_compute_enable_code_interpreter',
        string='Enable Code Interpreter',
        help=(
            "Let the LLM run sandboxed Python via the provider's native "
            'code-execution tool. Useful for analytics over tool results.'
        ),
        readonly=False,
        store=True,
        tracking=True,
    )

    read_only = fields.Boolean(
        string='Restrict to Read-only Tools',
        help='Restrict tool calls to read-only tools (enforced via MCP scope).',
        default=False,
        tracking=True,
    )

    allow_handoff = fields.Boolean(
        string='Allow Handoff',
        help=(
            'Expose this agent as a target for the switch_agent / list_agents '
            'handoff tools, so a router or another agent can hand the '
            'conversation to it.'
        ),
        default=False,
        tracking=True,
    )

    tool_filter = fields.Json(
        string='Tool Filter',
        help=('List of tool names this agent may call. Empty = all tools allowed.'),
        default=list,
    )

    essential_tool_names = fields.Json(
        string='Essential Tools',
        help=(
            'Tool names that ship with full schemas at session start. '
            'Every other catalog tool is name-only in the prompt and '
            'fetched on demand via tool_load. Empty falls back to a '
            'curated default (read primitives + navigation + ask_user). '
            'To disable lazy loading entirely, list every catalog tool. '
            'Names outside the tool filter are silently dropped.'
        ),
        default=list,
    )

    suggestion_ids = fields.One2many(
        comodel_name='muk_ai.agent.suggestion',
        string='Suggestions',
        help='Starter prompts shown in the empty chat for this agent.',
        copy=True,
        inverse_name='agent_id',
    )

    suggestions = fields.Json(
        compute='_compute_suggestions',
        string='Suggestions (JSON)',
    )

    tool_filter_options = fields.Json(
        compute='_compute_tool_filter_options',
        string='Available Tool Options',
    )

    approval_mode = fields.Selection(
        selection=[
            ('ask', 'Ask on writes'),
            ('off', 'Never ask'),
        ],
        string='Approval Mode',
        help=(
            '`ask` prompts before risky writes (deletes, workflow methods, '
            'audited-field updates, high-impact creates). `off` disables '
            'approvals entirely.'
        ),
        required=True,
        default='ask',
        tracking=True,
    )

    reasoning_effort = fields.Selection(
        compute='_compute_reasoning_effort',
        selection=REASONING_EFFORT_SELECTION,
        string='Reasoning Effort',
        help=(
            'How much the model thinks before answering. Lower tiers respond '
            'fastest and suit quick assistants and voice; higher tiers reason '
            'deepest for hard analytical work. Empty applies the default of '
            'the selected model.'
        ),
        readonly=False,
        store=True,
        tracking=True,
    )

    reasoning_effort_options = fields.Json(
        compute='_compute_reasoning_effort_options',
        string='Available Effort Options',
    )

    session_count = fields.Integer(
        compute='_compute_session_count',
        string='Sessions',
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _get_default(self) -> AIAgent:
        """Return the company default agent, or the first active one."""
        preferred = self.env.company.default_ai_agent_id
        if preferred and preferred.active:
            return preferred
        return self.search([('active', '=', True)], limit=1)

    @api.model
    def _prompt_eval_context(self) -> dict:
        """Extend the prompt context with Odoo version information."""
        ctx = super()._prompt_eval_context()
        ctx.update(
            {
                'odoo_version': release.version,
                'odoo_series': release.series,
            }
        )
        return ctx

    @api.model
    def _get_default_essential_tool_names(self) -> list[str]:
        """Return the curated default set of essential tool names."""
        return [
            'ask_user',
            'describe_model',
            'list_models',
            'open_action',
            'open_record',
            'open_view',
            'read_group',
            'read_records',
            'search_count',
            'search_read',
        ]

    def _build_system_prompt(self, session: models.BaseModel | None = None) -> str:
        """Render the agent's system prompt with optional session extras."""
        extras = session._session_prompt_extras() if session else {}
        return self._render_prompt(self.system_prompt or '', **extras)

    def _get_essential_tool_names(self) -> list[str]:
        """Return the configured essential tool names, or the default set."""
        self.ensure_one()
        configured = [
            str(name).strip()
            for name in (self.essential_tool_names or [])
            if isinstance(name, (str, int)) and str(name).strip()
        ]
        if configured:
            return configured
        return self._get_default_essential_tool_names()

    def _resolve_model(self) -> models.BaseModel:
        """Return the agent's model, falling back to the provider default."""
        if self.model_id:
            return self.model_id
        provider = self.env['muk_ai.provider']._get_default()
        return provider.default_model_id if provider else self.env['muk_ai.model']

    def _resolve_context_window(self) -> int:
        """Return the resolved model's context window, or the default."""
        model = self._resolve_model()
        return (model.context_window if model else 0) or DEFAULT_CONTEXT_WINDOW

    def _get_placeholder_filename(self, field: str) -> str:
        """Return the placeholder image filename for image fields."""
        if field in ('image_1920', 'image_1024', 'image_512', 'image_256', 'image_128'):
            return 'muk_ai/static/description/icon.png'
        return super()._get_placeholder_filename(field)

    # ----------------------------------------------------------
    # Actions
    # ----------------------------------------------------------

    def action_open_sessions(self) -> dict:
        """Return an action listing this agent's sessions."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Sessions'),
            'res_model': 'muk_ai.session',
            'view_mode': 'list,form',
            'domain': [('agent_id', '=', self.id)],
            'context': {'default_agent_id': self.id},
        }

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    def apply_tool_filter(self, tools: list[dict]) -> list[dict]:
        """Return only the tools permitted by this agent's filter."""
        allowed = self.tool_filter or []
        if not allowed:
            return tools
        allowed_set = set(allowed)
        return [t for t in tools if t.get('name') in allowed_set]

    # ----------------------------------------------------------
    # Compute
    # ----------------------------------------------------------

    @api.depends('model_id.provider_id')
    def _compute_provider_capabilities(self) -> None:
        """Reflect the resolved provider's capability flags onto the agent."""
        default_provider = self.env['muk_ai.provider']._get_default()
        self.mapped('model_id.provider_id')
        for record in self:
            provider = record.model_id.provider_id or default_provider
            record.supports_web_search = provider.supports_web_search
            record.supports_image_generation = provider.supports_image_generation
            record.supports_code_interpreter = provider.supports_code_interpreter

    @api.depends('model_id', 'supports_web_search')
    def _compute_enable_web_search(self) -> None:
        """Disable web search when the resolved model cannot support it."""
        for record in self:
            if (
                record.model_id
                and not record.supports_web_search
                and record.enable_web_search
            ):
                record.enable_web_search = False

    @api.depends('model_id', 'supports_image_generation')
    def _compute_enable_image_generation(self) -> None:
        """Disable image generation when the model cannot support it."""
        for record in self:
            if (
                record.model_id
                and not record.supports_image_generation
                and record.enable_image_generation
            ):
                record.enable_image_generation = False

    @api.depends('model_id', 'supports_code_interpreter')
    def _compute_enable_code_interpreter(self) -> None:
        """Disable the code interpreter when the model cannot support it."""
        for record in self:
            if (
                record.model_id
                and not record.supports_code_interpreter
                and record.enable_code_interpreter
            ):
                record.enable_code_interpreter = False

    @api.depends('model_id.reasoning_efforts')
    def _compute_reasoning_effort_options(self) -> None:
        """Expose the selected model's supported effort tiers to the picker."""
        tiers = dict(REASONING_EFFORT_SELECTION)
        for record in self:
            record.reasoning_effort_options = [
                tier
                for tier in record.model_id.reasoning_efforts or []
                if tier in tiers
            ]

    @api.depends('model_id', 'reasoning_effort_options')
    def _compute_reasoning_effort(self) -> None:
        """Drop the stored effort when the resolved model cannot support it."""
        for record in self:
            supported = record.reasoning_effort_options or []
            if record.reasoning_effort and record.reasoning_effort not in supported:
                record.reasoning_effort = False

    @api.depends(
        'suggestion_ids.label', 'suggestion_ids.prompt', 'suggestion_ids.sequence'
    )
    def _compute_suggestions(self) -> None:
        """Project the suggestion lines into a serializable list."""
        for record in self:
            record.suggestions = [
                {'label': s.label, 'prompt': s.prompt} for s in record.suggestion_ids
            ]

    @api.depends_context('lang')
    def _compute_tool_filter_options(self) -> None:
        """Build the selectable tool options from the Odoo tool index."""
        index = get_tool_index(self.env, registry='odoo')
        seen = {
            name: {
                'name': name,
                'category': entry.get('category') or '',
                'description': entry.get('description') or '',
            }
            for name, entry in index.items()
        }
        seen.setdefault(
            'ask_user',
            {
                'name': 'ask_user',
                'category': 'read',
                'description': _('Ask the user a question.'),
            },
        )
        options = sorted(seen.values(), key=lambda o: o['name'])
        for record in self:
            record.tool_filter_options = options

    def _compute_session_count(self) -> None:
        """Count the sessions linked to each agent."""
        grouped = self.env['muk_ai.session']._read_group(
            domain=[('agent_id', 'in', self.ids)],
            groupby=['agent_id'],
            aggregates=['__count'],
        )
        counts = {agent.id: count for agent, count in grouped}
        for record in self:
            record.session_count = counts.get(record.id, 0)
