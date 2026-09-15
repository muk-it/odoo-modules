from __future__ import annotations

from odoo import _, api, fields, models, release

from odoo.addons.muk_ai.tools import REASONING_EFFORT_SELECTION, search_backend
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
    )

    provider_id = fields.Many2one(
        comodel_name='muk_ai.provider',
        string='Provider',
        help=(
            'Pin this agent to a vendor without naming an exact model: every '
            'modality then prefers the default of that provider and falls '
            'back elsewhere only when it catalogues no model of that kind. '
            'Leave empty to follow the company default provider, else the '
            'first provider in the list.'
        ),
        domain=[('active', '=', True)],
        ondelete='set null',
        tracking=True,
    )

    model_id = fields.Many2one(
        comodel_name='muk_ai.model',
        string='Chat Model',
        help=(
            'Exact model this agent talks to, overriding the pinned provider. '
            'Leave empty to use the default chat model of the pinned provider, '
            'else of the company default provider, else of the first provider '
            'in the list that has one.'
        ),
        domain=[('modality', '=', 'chat')],
        ondelete='set null',
        tracking=True,
    )

    model_placeholder = fields.Char(
        compute='_compute_model_placeholders',
        string='Model Placeholder',
    )

    image_model_id = fields.Many2one(
        comodel_name='muk_ai.model',
        string='Image Model',
        help=(
            'Model that renders the images of this agent. Leave empty to use '
            'the default image model of the pinned provider, else of the '
            'company default provider, else of the first provider in the list '
            'that has one.'
        ),
        domain=[('modality', '=', 'image')],
        ondelete='set null',
        tracking=True,
    )

    image_model_placeholder = fields.Char(
        compute='_compute_model_placeholders',
        string='Image Model Placeholder',
    )

    web_search = fields.Selection(
        selection=[
            ('off', 'Off'),
            ('auto', 'Automatic'),
            ('native', 'Provider Built-in'),
            ('tool', 'Search Backend'),
        ],
        string='Web Search',
        help=(
            'How this agent searches the web. "Automatic" prefers the Web '
            'Search Backend set in the settings and falls back to the '
            'built-in search of the provider. The two explicit routes are '
            'never substituted: when the one picked here cannot serve, the '
            'agent searches nothing and the warning above says why.'
        ),
        required=True,
        default='off',
        tracking=True,
    )

    enable_image_generation = fields.Boolean(
        string='Enable Image Generation',
        help='Let the LLM generate images with the resolved image model.',
        tracking=True,
    )

    enable_code_interpreter = fields.Boolean(
        string='Enable Code Interpreter',
        help=(
            "Let the LLM run sandboxed Python via the provider's native "
            'code-execution tool. Useful for analytics over tool results.'
        ),
        tracking=True,
    )

    code_interpreter_performer = fields.Char(
        compute='_compute_code_interpreter_performer',
        string='Code Interpreter Performer',
    )

    capability_warning = fields.Text(
        compute='_compute_capability_warning',
        string='Capability Warning',
    )

    read_only = fields.Boolean(
        string='Read-only Mode',
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
            'curated default. Names outside the tool filter are dropped.'
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

    essential_tool_options = fields.Json(
        compute='_compute_essential_tool_options',
        string='Available Essential Options',
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
            'read_resource',
            'search_count',
            'search_read',
        ]

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

    @api.model
    def _rule_governed_tool_names(self) -> set[str]:
        """Return the tools the session loads itself, whatever the agent stores."""
        index = get_tool_index(self.env, registry='odoo')
        return {
            'ask_user',
            *self.env['muk_ai.session']._eager_tool_name_registry(),
        } | {
            name
            for name, entry in index.items()
            if (entry.get('meta') or {}).get('execute') == 'client'
        }

    def _leading_provider(self) -> models.BaseModel:
        """Return the provider that leads the default walk of every modality.

        A pinned provider is the admin's choice and leads. Without one the
        chat pick's provider leads, so an agent on Gemini draws with Gemini
        unless told otherwise.
        """
        return self.provider_id or self.model_id.provider_id

    def _default_model_for(self, modality: str) -> models.BaseModel:
        """Return the model an empty picker of the modality resolves to.

        The pinned provider answers first and is honoured even when it cannot
        authenticate — a pin is a choice, every step of the fallback walk is not.
        """
        return self.provider_id._default_model(modality) or self.env[
            'muk_ai.model'
        ]._default_for(modality, first=self._leading_provider())

    def _resolve_model_for(self, modality: str) -> models.BaseModel:
        """Return the agent's pick for the modality, else its default.

        An archived pick is retired: it falls back to the default and
        ``capability_warning`` names it. Image stays empty while image
        generation is off.
        """
        if modality == 'image' and not self.enable_image_generation:
            return self.env['muk_ai.model']
        field = 'model_id' if modality == 'chat' else f'{modality}_model_id'
        return self[field].filtered('active') or self._default_model_for(modality)

    def _default_model_placeholder(self, modality: str) -> str:
        """Name the model an empty picker of the modality resolves to."""
        if record := self._default_model_for(modality):
            return _('Default: %(model)s', model=record.display_name)
        field = self.env['muk_ai.model']._fields['modality']
        labels = dict(field._description_selection(self.env))
        return _('No %(modality)s model available', modality=labels[modality].lower())

    def _resolve_provider(self) -> models.BaseModel:
        """Return the provider backing the resolved model, else the pinned or default one."""
        if model := self._resolve_model_for('chat'):
            return model.provider_id
        return self.provider_id or self.env['muk_ai.provider']._get_default()

    def _serves_builtin_tools(self) -> bool:
        """Return whether the resolved model runs its vendor's built-in tools.

        Provider-level support is not enough: a model that cannot combine the
        vendor's connectors with function calling serves none of them, since
        a session always declares its Odoo tools.
        """
        provider = self._resolve_provider()
        return bool(provider) and provider._serves_builtin_tools(
            self._resolve_model_for('chat').technical_name
        )

    def _admits_tool(self, name: str) -> bool:
        """Return whether the tool filter of this agent lets the tool through."""
        return not self.tool_filter or name in self.tool_filter

    def _served_web_search_routes(self) -> dict[str, bool]:
        """Map each web search route to whether anything can currently serve it.

        Insertion order is the preference ``auto`` applies.
        """
        return {
            'tool': self._admits_tool('web_search')
            and search_backend(self.env) is not None,
            'native': self._resolve_provider().supports_web_search
            and self._serves_builtin_tools(),
        }

    def _web_search_route(self) -> str | None:
        """Return ``'tool'``, ``'native'`` or ``None``, honouring the chosen route.

        ``auto`` prefers a configured backend and falls back to the built-in
        connector. An explicit route is never substituted: when nothing can
        serve it the agent searches nothing and ``capability_warning`` says so.
        """
        if self.web_search in (False, 'off'):
            return None
        served = self._served_web_search_routes()
        if self.web_search == 'auto':
            return next((route for route, ok in served.items() if ok), None)
        return self.web_search if served[self.web_search] else None

    def _web_search_warning(self) -> str | None:
        """Explain why the chosen web search route cannot serve, or return ``None``.

        Each route names the one thing that is missing and the one setting
        that repairs it, so the admin never has to guess which of the two
        halves of the route failed.
        """
        if self.web_search == 'off' or self._web_search_route():
            return None
        if self.web_search == 'native':
            return _(
                'Web search is set to "Provider Built-in", but the model this '
                'agent runs on serves no built-in search. Pick a model that '
                'has one, or switch to "Search Backend".'
            )
        if search_backend(self.env) is not None:
            return _(
                'Web search would run through the Web Search Backend, but the '
                'tool filter of this agent does not list "web_search", so the '
                'tool never reaches the model. Add it on the Tools page, or '
                'clear the filter.'
            )
        if self.web_search == 'tool':
            return _(
                'Web search is set to "Search Backend", but no Web Search '
                'Backend is configured. Set one in the MuK AI settings, or '
                'switch to "Provider Built-in".'
            )
        return _(
            'Web search is enabled, but the model this agent runs on serves no '
            'built-in search and no Web Search Backend is set. Set one in the '
            'MuK AI settings, or pick a model that has one.'
        )

    def _code_interpreter_route(self) -> str | None:
        """Return ``'native'`` when the resolved model runs code, else ``None``.

        Code execution is a vendor-side tool of the provider implementation:
        no backend can stand in for it the way one does for web search.
        """
        if not self.enable_code_interpreter:
            return None
        if self._resolve_provider().supports_code_interpreter:
            return 'native' if self._serves_builtin_tools() else None
        return None

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
        return [tool for tool in tools if self._admits_tool(tool.get('name'))]

    # ----------------------------------------------------------
    # Compute
    # ----------------------------------------------------------

    @api.depends('provider_id', 'model_id')
    def _compute_model_placeholders(self) -> None:
        """Name what an empty chat or image picker resolves to."""
        for record in self:
            record.model_placeholder = record._default_model_placeholder('chat')
            record.image_model_placeholder = record._default_model_placeholder('image')

    @api.depends(
        'enable_code_interpreter',
        'model_id.active',
        'model_id.technical_name',
        'model_id.provider_id',
        'model_id.provider_id.api_key',
        'provider_id',
        'provider_id.api_key',
    )
    def _compute_code_interpreter_performer(self) -> None:
        """Name the vendor whose servers run the code of this agent."""
        for record in self:
            if not record.enable_code_interpreter:
                record.code_interpreter_performer = False
            elif record._code_interpreter_route():
                record.code_interpreter_performer = _(
                    'Runs on %(provider)s',
                    provider=record._resolve_provider().display_name,
                )
            else:
                record.code_interpreter_performer = _('No provider runs code here')

    @api.depends(
        'web_search',
        'tool_filter',
        'enable_image_generation',
        'enable_code_interpreter',
        'image_model_id.active',
        'image_model_id.provider_id',
        'image_model_id.provider_id.api_key',
        'model_id.active',
        'model_id.technical_name',
        'model_id.provider_id',
        'model_id.provider_id.api_key',
        'model_id.provider_id.api_region',
        'provider_id',
        'provider_id.api_key',
        'provider_id.api_region',
    )
    def _compute_capability_warning(self) -> None:
        """Name every enabled capability that nothing serves, and its fix."""
        labels = {
            name: self._fields[name].get_description(self.env, ['string'])['string']
            for name in ('model_id', 'image_model_id')
        }
        for record in self:
            warnings = []
            if record.provider_id and not record.provider_id._can_serve():
                warnings.append(
                    _(
                        'This agent is pinned to %(provider)s, which has no API '
                        'key configured. A pinned provider is never swapped for '
                        'another vendor: set the key on %(provider)s, or clear '
                        'the pin.',
                        provider=record.provider_id.display_name,
                    )
                )
            if (
                record.provider_id
                and record.model_id
                and record.model_id.provider_id != record.provider_id
            ):
                warnings.append(
                    _(
                        'Model %(model)s runs on %(vendor)s, so it overrides the '
                        'pinned provider %(provider)s for chat. Pick a model of '
                        '%(provider)s, or clear the model to follow the pin.',
                        model=record.model_id.display_name,
                        vendor=record.model_id.provider_id.display_name,
                        provider=record.provider_id.display_name,
                    )
                )
            picks = ['model_id']
            if record.enable_image_generation:
                picks.append('image_model_id')
            for name in picks:
                if not (picked := record[name]):
                    continue
                if not picked.active:
                    warnings.append(
                        _(
                            '%(label)s %(model)s is archived, so this agent falls '
                            'back to the default model. Pick an active model here, '
                            'or restore %(model)s.',
                            label=labels[name],
                            model=picked.display_name,
                        )
                    )
                elif not picked.provider_id._can_serve():
                    warnings.append(
                        _(
                            '%(label)s %(model)s runs on %(provider)s, which has '
                            'no API key configured. A model picked here is never '
                            'served by another vendor instead: set the key on '
                            '%(provider)s, or pick a model from a configured '
                            'provider.',
                            label=labels[name],
                            model=picked.display_name,
                            provider=picked.provider_id.display_name,
                        )
                    )
            if warning := record._web_search_warning():
                warnings.append(warning)
            image = record._resolve_model_for('image')
            if image and not record._admits_tool('generate_image'):
                warnings.append(
                    _(
                        'Image generation is enabled, but the tool filter of this '
                        'agent does not list "generate_image", so the tool never '
                        'reaches the model. Add it on the Tools page, or clear '
                        'the filter.'
                    )
                )
            if record.enable_image_generation and not image:
                hidden = self.env['muk_ai.model']._default_for(
                    'image',
                    first=record._leading_provider(),
                    configured=False,
                )
                if hidden:
                    warnings.append(
                        _(
                            'Image generation is enabled, but the image model it '
                            'would draw with runs on %(provider)s, which has no '
                            'API key configured. Set the key there, or pick a '
                            'model from a configured provider.',
                            provider=hidden.provider_id.display_name,
                        )
                    )
                else:
                    warnings.append(
                        _(
                            'Image generation is enabled, but no image model '
                            'resolves. Set a Default Image Model on a provider, '
                            'or pick one here.'
                        )
                    )
            if record.enable_code_interpreter and not record._code_interpreter_route():
                warnings.append(
                    _(
                        'Code interpreter is enabled, but the model picked here '
                        'runs no code-execution tool. No setting can add one: '
                        'pick a model that has one.'
                    )
                )
            record.capability_warning = '\n'.join(warnings)

    @api.depends('provider_id', 'model_id', 'model_id.reasoning_efforts')
    def _compute_reasoning_effort_options(self) -> None:
        """Expose the resolved model's supported effort tiers to the picker.

        The tiers follow the model the turn actually runs on, so an agent
        that leans on a default still offers the effort its model supports.
        """
        tiers = dict(REASONING_EFFORT_SELECTION)
        for record in self:
            model = record._resolve_model_for('chat')
            record.reasoning_effort_options = [
                tier for tier in model.reasoning_efforts or [] if tier in tiers
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

    @api.depends('tool_filter_options')
    def _compute_essential_tool_options(self) -> None:
        """Offer only the tools whose eager loading this field decides."""
        governed = self._rule_governed_tool_names()
        for record in self:
            record.essential_tool_options = [
                option
                for option in record.tool_filter_options
                if option['name'] not in governed
            ]

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
