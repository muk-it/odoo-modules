from __future__ import annotations

from collections.abc import Callable

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from odoo.addons.muk_ai.providers import REGISTRY
from odoo.addons.muk_ai.providers.base import ProviderBase
from odoo.addons.muk_ai.providers.region import CUSTOM
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

    def _selection_api_region(self) -> list[tuple[str, str]]:
        """Return the union of every registered region, first label winning."""
        labels = {'default': _('Provider Default')}
        for cls in REGISTRY.values():
            for region in cls.regions:
                labels.setdefault(region.code, _(region.label))
        labels.setdefault(CUSTOM.code, _(CUSTOM.label))
        return list(labels.items())

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    name = fields.Selection(
        selection=lambda self: self._selection_name(),
        string='Provider',
        readonly=True,
        required=True,
    )

    code = fields.Char(
        string='Code',
        required=True,
        default='default',
        copy=False,
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

    api_region = fields.Selection(
        compute='_compute_api_region',
        precompute=True,
        selection=lambda self: self._selection_api_region(),
        string='Region',
        readonly=False,
        required=True,
        store=True,
    )

    api_region_options = fields.Json(
        compute='_compute_api_region_options',
        string='Region Options',
    )

    api_url = fields.Char(
        string='Custom URL',
        help='Endpoint base URL used when the region is set to Custom URL.',
        groups='base.group_system',
    )

    api_endpoint = fields.Char(
        compute='_compute_api_endpoint',
        string='Endpoint',
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

    def _valid_regions(self) -> list[str]:
        """Return the region codes the provider implementation accepts."""
        self.ensure_one()
        if (impl := REGISTRY.get(self.name)) is None:
            return []
        codes = ['default'] if impl.default_url else []
        return codes + [region.code for region in impl.regions]

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

    @api.depends('name', 'code')
    def _compute_display_name(self) -> None:
        """Set the display name from the provider label, suffixed by a non-default code."""
        labels = dict(self._fields['name']._description_selection(self.env))
        for record in self:
            label = labels.get(record.name) or record.name or ''
            if record.code and record.code != 'default':
                label = f'{label} ({record.code})'
            record.display_name = label

    @api.depends('name')
    def _compute_api_region(self) -> None:
        """Seed the region and repair one the implementation does not offer.

        A region the implementation declares is an admin's choice and stays.
        The implementation of a provider whose addon loads after this one is
        not registered yet while an upgrade seeds the column, so such a record
        is seeded once from its stored URL instead of the class default.
        """
        for record in self:
            if (impl := REGISTRY.get(record.name)) is not None:
                if record.api_region not in record._valid_regions():
                    record.api_region = 'default' if impl.default_url else 'custom'
            elif not record.api_region:
                record.api_region = 'custom' if record.api_url else 'default'

    @api.depends('name')
    def _compute_api_region_options(self) -> None:
        """Expose the selectable regions, empty when there is nothing to choose."""
        for record in self:
            codes = record._valid_regions()
            record.api_region_options = codes if codes != ['default'] else []

    @api.depends('name', 'api_region', 'api_url')
    def _compute_api_endpoint(self) -> None:
        """Resolve the exact base URL the HTTP layer will use."""
        for record in self:
            record.api_endpoint = (
                record._get_client().api_url if record.name in REGISTRY else ''
            )

    @api.depends('name', 'api_region')
    def _compute_capabilities(self) -> None:
        """Reflect the registry capability flags, minus those the region disables."""
        for record in self:
            impl = REGISTRY.get(record.name)
            region = impl.region(record.api_region) if impl else None
            disabled = region.disabled if region else ()
            record.supports_web_search = bool(
                impl and impl.supports_web_search and 'web_search' not in disabled
            )
            record.supports_image_generation = bool(
                impl
                and impl.supports_image_generation
                and 'image_generation' not in disabled
            )
            record.supports_code_interpreter = bool(
                impl
                and impl.supports_code_interpreter
                and 'code_interpreter' not in disabled
            )
            record.supports_vision = bool(impl and impl.supports_vision)

    # ----------------------------------------------------------
    # Constraints
    # ----------------------------------------------------------

    @api.constrains('name', 'api_region', 'api_url')
    def _check_api_region(self) -> None:
        """Reject a region the implementation lacks or a custom region without URL.

        A provider whose addon has not registered its implementation yet
        (its module loads after this one during an upgrade) has nothing to
        validate against and is skipped.
        """
        for record in self:
            if record.name not in REGISTRY:
                continue
            if record.api_region not in record._valid_regions():
                raise ValidationError(
                    _(
                        'Region %(region)s is not available for provider %(provider)s.',
                        region=record.api_region,
                        provider=record.name,
                    )
                )
            if record.api_region == 'custom' and not record.api_url:
                raise ValidationError(
                    _('A custom URL is required when the region is set to Custom URL.')
                )

    _unique_name = models.Constraint(
        'unique(name, code)',
        'A provider with this name and code already exists.',
    )

    # ----------------------------------------------------------
    # ORM methods
    # ----------------------------------------------------------

    def unlink(self) -> bool:
        """Delete the providers, refusing the ones an addon ships.

        :raise UserError: when a record carries an external identifier, since
            its implementation stays registered and no upgrade recreates the
            record once it is gone
        """
        shipped = (
            self.env['ir.model.data']
            .sudo()
            .search([('model', '=', self._name), ('res_id', 'in', self.ids)])
        )
        if shipped:
            raise UserError(
                _(
                    'These providers ship with their addon and cannot be '
                    'deleted: %(providers)s. Archive them instead.',
                    providers=', '.join(
                        self.browse(shipped.mapped('res_id')).mapped('display_name')
                    ),
                )
            )
        return super().unlink()
