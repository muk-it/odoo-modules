from odoo import _, api, fields, models

from odoo.addons.muk_ai.tools.limits import DEFAULT_CONTEXT_WINDOW
from odoo.addons.muk_mcp.core.tool import get_tool_index


class AIAgent(models.Model):

    _name = 'muk_ai.agent'
    _description = "AI Agent"
    _inherit = [
        'image.mixin',
        'mail.thread',
        'mail.activity.mixin',
    ]
    _order = 'sequence, name'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    name = fields.Char(
        string="Name",
        required=True,
        translate=True,
        tracking=True,
    )

    active = fields.Boolean(
        string="Active",
        default=True,
        tracking=True,
    )

    sequence = fields.Integer(
        string="Sequence",
        default=10,
    )

    description = fields.Text(
        string="Description",
        translate=True,
    )

    system_prompt = fields.Text(
        string="System Prompt",
        translate=True,
    )

    model_id = fields.Many2one(
        comodel_name='muk_ai.model',
        string="Model",
        help=(
            "Model used by this agent. "
            "Leave empty to use the company default model."
        ),
        ondelete='set null',
        tracking=True,
    )

    supports_web_search = fields.Boolean(
        compute='_compute_provider_capabilities',
        string="Supports Web Search",
    )

    supports_image_generation = fields.Boolean(
        compute='_compute_provider_capabilities',
        string="Supports Image Generation",
    )

    supports_code_interpreter = fields.Boolean(
        compute='_compute_provider_capabilities',
        string="Supports Code Interpreter",
    )

    enable_web_search = fields.Boolean(
        compute='_compute_enable_web_search',
        string="Enable Web Search",
        help="Let the LLM use the provider's native web search tool.",
        readonly=False,
        store=True,
        tracking=True,
    )

    enable_image_generation = fields.Boolean(
        compute='_compute_enable_image_generation',
        string="Enable Image Generation",
        help="Let the LLM generate images via the provider's native tool.",
        readonly=False,
        store=True,
        tracking=True,
    )

    enable_code_interpreter = fields.Boolean(
        compute='_compute_enable_code_interpreter',
        string="Enable Code Interpreter",
        help=(
            "Let the LLM run sandboxed Python via the provider's native "
            "code-execution tool. Useful for analytics over tool results."
        ),
        readonly=False,
        store=True,
        tracking=True,
    )

    read_only = fields.Boolean(
        string="Restrict to Read-only Tools",
        help="Restrict tool calls to read-only tools (enforced via MCP scope).",
        default=False,
        tracking=True,
    )

    tool_filter = fields.Json(
        string="Tool Filter",
        help=(
            "List of tool names this agent may call. "
            "Empty = all tools allowed."
        ),
        default=list,
    )

    suggestion_ids = fields.One2many(
        comodel_name='muk_ai.agent.suggestion',
        string="Suggestions",
        help="Starter prompts shown in the empty chat for this agent.",
        copy=True,
        inverse_name='agent_id',
    )

    suggestions = fields.Json(
        compute='_compute_suggestions',
        string="Suggestions (JSON)",
    )

    tool_filter_options = fields.Json(
        compute='_compute_tool_filter_options',
        string="Available Tool Options",
    )

    approval_mode = fields.Selection(
        selection=[
            ('ask', "Ask on writes"),
            ('off', "Never ask"),
        ],
        string="Approval Mode",
        help=(
            "`ask` prompts before risky writes (deletes, workflow methods, "
            "audited-field updates, high-impact creates). `off` disables "
            "approvals entirely."
        ),
        required=True,
        default='ask',
        tracking=True,
    )

    session_count = fields.Integer(
        compute='_compute_session_count',
        string="Sessions",
    )

    revision_count = fields.Integer(
        compute='_compute_revision_count',
        string="Prompt Revisions",
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _get_default(self):
        preferred = self.env.company.default_ai_agent_id
        if preferred and preferred.active:
            return preferred
        return self.search([('active', '=', True)], limit=1)

    def _resolve_model(self):
        if self.model_id:
            return self.model_id
        provider = self.env['muk_ai.provider']._get_default()
        return (
            provider.default_model_id
            if provider else self.env['muk_ai.model']
        )

    def _resolve_context_window(self):
        model = self._resolve_model()
        return (
            (model.context_window if model else 0) or
            DEFAULT_CONTEXT_WINDOW
        )

    def _get_placeholder_filename(self, field):
        if field in ('image_1920', 'image_1024', 'image_512', 'image_256', 'image_128'):
            return 'muk_ai/static/description/icon.png'
        return super()._get_placeholder_filename(field)

    # ----------------------------------------------------------
    # Actions
    # ----------------------------------------------------------

    def action_open_sessions(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Sessions"),
            'res_model': 'muk_ai.session',
            'view_mode': 'list,form',
            'domain': [('agent_id', '=', self.id)],
            'context': {'default_agent_id': self.id},
        }

    def action_open_prompt_revisions(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Prompt History"),
            'res_model': 'muk_ai.agent.revision',
            'view_mode': 'list,form',
            'domain': [('agent_id', '=', self.id)],
            'context': {'default_agent_id': self.id},
        }

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    def apply_tool_filter(self, tools):
        allowed = self.tool_filter or []
        if not allowed:
            return tools
        allowed_set = set(allowed)
        return [t for t in tools if t.get('name') in allowed_set]

    # ----------------------------------------------------------
    # Compute
    # ----------------------------------------------------------

    @api.depends('model_id.provider_id')
    def _compute_provider_capabilities(self):
        default_provider = self.env['muk_ai.provider']._get_default()
        self.mapped('model_id.provider_id')
        for record in self:
            provider = record.model_id.provider_id or default_provider
            record.supports_web_search = provider.supports_web_search
            record.supports_image_generation = provider.supports_image_generation
            record.supports_code_interpreter = provider.supports_code_interpreter

    @api.depends('model_id', 'supports_web_search')
    def _compute_enable_web_search(self):
        for record in self:
            if (record.model_id
                    and not record.supports_web_search
                    and record.enable_web_search):
                record.enable_web_search = False

    @api.depends('model_id', 'supports_image_generation')
    def _compute_enable_image_generation(self):
        for record in self:
            if (record.model_id
                    and not record.supports_image_generation
                    and record.enable_image_generation):
                record.enable_image_generation = False

    @api.depends('model_id', 'supports_code_interpreter')
    def _compute_enable_code_interpreter(self):
        for record in self:
            if (record.model_id
                    and not record.supports_code_interpreter
                    and record.enable_code_interpreter):
                record.enable_code_interpreter = False

    @api.depends(
        'suggestion_ids.label',
        'suggestion_ids.prompt',
        'suggestion_ids.sequence'
    )
    def _compute_suggestions(self):
        for record in self:
            record.suggestions = [
                {'label': s.label, 'prompt': s.prompt}
                for s in record.suggestion_ids
            ]

    @api.depends_context('lang')
    def _compute_tool_filter_options(self):
        index = get_tool_index(self.env, registry='odoo')
        seen = {
            name: {
                'name': name,
                'category': entry.get('category') or '',
                'description': entry.get('description') or '',
            }
            for name, entry in index.items()
        }
        seen.setdefault('ask_user', {
            'name': 'ask_user',
            'category': 'read',
            'description': _("Ask the user a question."),
        })
        options = sorted(seen.values(), key=lambda o: o['name'])
        for record in self:
            record.tool_filter_options = options

    def _compute_session_count(self):
        grouped = self.env['muk_ai.session']._read_group(
            domain=[('agent_id', 'in', self.ids)],
            groupby=['agent_id'],
            aggregates=['__count'],
        )
        counts = {agent.id: count for agent, count in grouped}
        for record in self:
            record.session_count = counts.get(record.id, 0)

    def _compute_revision_count(self):
        grouped = self.env['muk_ai.agent.revision'].sudo()._read_group(
            domain=[('agent_id', 'in', self.ids)],
            groupby=['agent_id'],
            aggregates=['__count'],
        )
        counts = {agent.id: count for agent, count in grouped}
        for record in self:
            record.revision_count = counts.get(record.id, 0)

    # ----------------------------------------------------------
    # ORM
    # ----------------------------------------------------------

    def write(self, vals):
        if 'system_prompt' in vals:
            for record in self:
                old = record.system_prompt or ''
                if old and old != (vals['system_prompt'] or ''):
                    self.env['muk_ai.agent.revision'].sudo().create({
                        'agent_id': record.id,
                        'body': old,
                    })
        return super().write(vals)


