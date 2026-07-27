from __future__ import annotations

from collections.abc import Callable

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.muk_ai.providers import REGISTRY
from odoo.addons.muk_ai.providers.base import ProviderBase
from odoo.addons.muk_ai.tools import (
    is_unmaterialized_attachment,
    nearest_reasoning_effort,
)


class AIProvider(models.Model):
    """Configured LLM provider account exposing a streaming request client."""

    _name = 'muk_ai.provider'
    _description = 'AI Provider'
    _order = 'sequence, name'

    # ----------------------------------------------------------
    # Selections
    # ----------------------------------------------------------

    def _selection_name(self) -> list[tuple[str, str]]:
        """Return the selection of registered provider names and labels."""
        return [(cls.name, cls.label) for cls in REGISTRY.values()]

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    name = fields.Selection(
        selection=lambda self: self._selection_name(),
        string='Provider',
        readonly=True,
        required=True,
    )

    active = fields.Boolean(
        string='Active',
        default=True,
    )

    sequence = fields.Integer(
        string='Sequence',
        default=10,
    )

    api_key = fields.Char(
        string='API Key',
        help='Authentication token for this provider.',
        groups='base.group_system',
    )

    max_tokens = fields.Integer(
        string='Max Tokens',
        help='Maximum completion tokens per request.',
        required=True,
        default=4096,
    )

    request_timeout = fields.Integer(
        string='Request Timeout',
        help='Provider request timeout in seconds.',
        required=True,
        default=60,
    )

    idle_timeout = fields.Integer(
        string='Idle Timeout',
        help='Seconds without a streamed chunk before aborting the connection.',
        required=True,
        default=45,
    )

    rate_limit = fields.Integer(
        string='Rate Limit',
        help='Max sessions a single user may create per minute. 0 = disabled.',
        required=True,
        default=10,
    )

    default_model_id = fields.Many2one(
        comodel_name='muk_ai.model',
        string='Default Model',
        help='Model used when an agent does not specify one.',
        domain="[('provider_id', '=', id)]",
    )

    model_ids = fields.One2many(
        comodel_name='muk_ai.model',
        string='Models',
        inverse_name='provider_id',
    )

    supports_web_search = fields.Boolean(
        compute='_compute_capabilities',
        string='Supports Web Search',
    )

    supports_image_generation = fields.Boolean(
        compute='_compute_capabilities',
        string='Supports Image Generation',
    )

    supports_code_interpreter = fields.Boolean(
        compute='_compute_capabilities',
        string='Supports Code Interpreter',
    )

    supports_vision = fields.Boolean(
        compute='_compute_capabilities',
        string='Supports Vision',
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _get_default(self) -> AIProvider:
        """Return the company default provider, or the first active one."""
        preferred = self.env.company.default_ai_provider_id
        if preferred and preferred.active:
            return preferred
        return self.search([('active', '=', True)], limit=1)

    def _get_client(self) -> ProviderBase:
        """Instantiate the provider client from the registry.

        :raise UserError: when no addon registers this provider
        """
        if (impl_cls := REGISTRY.get(self.name)) is None:
            raise UserError(
                _(
                    'AI provider %(provider)s is not supported. '
                    'Install an addon that registers it.',
                    provider=self.name,
                )
            )
        return impl_cls(provider=self)

    def _resolve_model_name(self, override: str | None = None) -> str:
        """Return the technical model name, honoring an explicit override."""
        return (
            override
            or self.default_model_id.technical_name
            or REGISTRY[self.name].default_model
        )

    def _effective_reasoning_effort(
        self,
        technical_name: str,
        effort: str | None,
    ) -> str | None:
        """Resolve the effort tier for the model, honoring its supported set.

        An uncatalogued model passes the requested tier through unchanged; a
        catalogued model without supported tiers has no effort knob at all
        and resolves to ``None``.
        """
        record = self.env['muk_ai.model'].search(
            [
                ('provider_id', '=', self.id),
                ('technical_name', '=', technical_name),
            ],
            limit=1,
        )
        if not record:
            return effort or None
        supported = record.reasoning_efforts or []
        if not supported:
            return None
        effort = effort or record.reasoning_effort_default
        if not effort:
            return None
        return nearest_reasoning_effort(effort, supported)

    def _build_request_extra(
        self,
        cache_key: str | None = None,
        reasoning_effort: str | None = None,
    ) -> dict:
        """Return provider-agnostic request metadata.

        :param cache_key: stable identifier a provider may use to route
            prompt-cache lookups (e.g. OpenAI ``prompt_cache_key``).
        :param reasoning_effort: thinking tier (``low``/``medium``/``high``)
            applied by providers on reasoning-capable models.
        """
        extra = {
            'metadata': {
                'odoo_user_id': self.env.uid,
            },
        }
        if cache_key:
            extra['cache_key'] = cache_key
        if reasoning_effort:
            extra['reasoning_effort'] = reasoning_effort
        return extra

    def _materialize_block(self, block: dict) -> dict:
        """Resolve an unmaterialized attachment block to its content."""
        if not is_unmaterialized_attachment(block):
            return block
        attachment = self.env['ir.attachment'].browse(
            block.get('attachment_id'),
        )
        if not attachment.exists():
            return {
                'type': 'input_text',
                'text': f'[Missing: {block.get("filename") or "unknown"}]',
            }
        return attachment._ai_materialize()

    def _materialize_item(self, item):
        """Materialize every attachment block inside a single input item."""
        content = item.get('content') if isinstance(item, dict) else None
        if not isinstance(content, list):
            return item
        return {**item, 'content': [self._materialize_block(b) for b in content]}

    def _materialize_inputs(self, inputs: list | None) -> list:
        """Materialize attachment blocks across all input items."""
        return [self._materialize_item(item) for item in inputs or []]

    def _request_responses(
        self,
        inputs: list,
        tools_schema: list | None = None,
        text_schema: dict | None = None,
        on_delta: Callable | None = None,
        model: str | None = None,
        enable_web_search: bool = False,
        enable_image_generation: bool = False,
        enable_code_interpreter: bool = False,
        cache_key: str | None = None,
        reasoning_effort: str | None = None,
    ) -> dict:
        """Send a streaming responses request through the provider client."""
        technical_name = self._resolve_model_name(model)
        return self._get_client().request(
            inputs=self._materialize_inputs(inputs),
            tools_schema=tools_schema,
            text_schema=text_schema,
            on_delta=on_delta,
            model=technical_name,
            enable_web_search=enable_web_search,
            enable_image_generation=enable_image_generation,
            enable_code_interpreter=enable_code_interpreter,
            extra=self._build_request_extra(
                cache_key=cache_key,
                reasoning_effort=self._effective_reasoning_effort(
                    technical_name,
                    reasoning_effort,
                ),
            ),
        )

    # ----------------------------------------------------------
    # Actions
    # ----------------------------------------------------------

    def action_test_connection(self) -> dict:
        """Test the provider connection and return a success notification."""
        self._get_client().test_connection()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'title': _('AI Provider'),
                'message': _(
                    'Connection to %(provider)s succeeded.',
                    provider=dict(self._selection_name()).get(
                        self.name,
                        self.name,
                    ),
                ),
                'sticky': False,
            },
        }

    # ----------------------------------------------------------
    # Compute
    # ----------------------------------------------------------

    @api.depends('name')
    def _compute_display_name(self) -> None:
        """Set the display name from the provider selection label."""
        labels = dict(self._fields['name']._description_selection(self.env))
        for record in self:
            record.display_name = labels.get(record.name) or record.name or ''

    @api.depends('name')
    def _compute_capabilities(self) -> None:
        """Reflect the registry capability flags onto the record."""
        for record in self:
            impl = REGISTRY.get(record.name)
            record.supports_web_search = bool(impl and impl.supports_web_search)
            record.supports_image_generation = bool(
                impl and impl.supports_image_generation
            )
            record.supports_code_interpreter = bool(
                impl and impl.supports_code_interpreter
            )
            record.supports_vision = bool(impl and impl.supports_vision)

    # ----------------------------------------------------------
    # Constraints
    # ----------------------------------------------------------

    _sql_constraints = [
        (
            'unique_name',
            'unique(name)',
            'A provider with this name already exists.',
        ),
    ]
