from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.muk_ai.providers import REGISTRY
from odoo.addons.muk_ai.tools import is_unmaterialized_attachment


class AIProvider(models.Model):

    _name = 'muk_ai.provider'
    _description = "AI Provider"
    _order = 'sequence, name'

    # ----------------------------------------------------------
    # Selections
    # ----------------------------------------------------------

    def _selection_name(self):
        return [(cls.name, cls.label) for cls in REGISTRY.values()]

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    name = fields.Selection(
        selection=lambda self: self._selection_name(),
        string="Provider",
        readonly=True,
        required=True,
    )

    active = fields.Boolean(
        string="Active",
        default=True,
    )

    sequence = fields.Integer(
        string="Sequence",
        default=10,
    )

    api_key = fields.Char(
        string="API Key",
        help="Authentication token for this provider.",
        groups="base.group_system",
    )

    max_tokens = fields.Integer(
        string="Max Tokens",
        help="Maximum completion tokens per request.",
        required=True,
        default=4096,
    )

    request_timeout = fields.Integer(
        string="Request Timeout",
        help="Provider request timeout in seconds.",
        required=True,
        default=60,
    )

    idle_timeout = fields.Integer(
        string="Idle Timeout",
        help="Seconds without a streamed chunk before aborting the connection.",
        required=True,
        default=45,
    )

    rate_limit = fields.Integer(
        string="Rate Limit",
        help="Max sessions a single user may create per minute. 0 = disabled.",
        required=True,
        default=10,
    )

    default_model_id = fields.Many2one(
        comodel_name='muk_ai.model',
        string="Default Model",
        help="Model used when an agent does not specify one.",
        domain="[('provider_id', '=', id)]",
    )

    model_ids = fields.One2many(
        comodel_name='muk_ai.model',
        string="Models",
        inverse_name='provider_id',
    )

    supports_web_search = fields.Boolean(
        compute='_compute_capabilities',
        string="Supports Web Search",
    )

    supports_image_generation = fields.Boolean(
        compute='_compute_capabilities',
        string="Supports Image Generation",
    )

    supports_code_interpreter = fields.Boolean(
        compute='_compute_capabilities',
        string="Supports Code Interpreter",
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _get_default(self):
        preferred = self.env.company.default_ai_provider_id
        if preferred and preferred.active:
            return preferred
        return self.search([('active', '=', True)], limit=1)

    def _get_client(self):
        if (impl_cls := REGISTRY.get(self.name)) is None:
            raise UserError(_(
                'AI provider %(provider)s is not supported. '
                'Install an addon that registers it.',
                provider=self.name,
            ))
        return impl_cls(
            api_key=self.sudo().api_key or '',
            request_timeout=self.request_timeout,
            idle_timeout=self.idle_timeout,
            max_tokens=self.max_tokens,
        )

    def _resolve_model_name(self, override=None):
        return (
            override
            or self.default_model_id.technical_name
            or REGISTRY[self.name].default_model
        )

    def _build_request_extra(self):
        return {
            'metadata': {
                'odoo_user_id': self.env.uid,
            },
        }

    def _materialize_block(self, block):
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
        content = (
            item.get('content')
            if isinstance(item, dict) else None
        )
        if not isinstance(content, list):
            return item
        return {
            **item,
            'content': [
                self._materialize_block(b) for b in content
            ]
        }

    def _materialize_inputs(self, inputs):
        return [self._materialize_item(item) for item in inputs or []]

    def _request_responses(
        self,
        inputs,
        tools_schema=None,
        text_schema=None,
        on_delta=None,
        model=None,
        enable_web_search=False,
        enable_image_generation=False,
        enable_code_interpreter=False
    ):
        return self._get_client().request(
            inputs=self._materialize_inputs(inputs),
            tools_schema=tools_schema,
            text_schema=text_schema,
            on_delta=on_delta,
            model=self._resolve_model_name(model),
            enable_web_search=enable_web_search,
            enable_image_generation=enable_image_generation,
            enable_code_interpreter=enable_code_interpreter,
            extra=self._build_request_extra(),
        )

    # ----------------------------------------------------------
    # Actions
    # ----------------------------------------------------------

    def action_test_connection(self):
        self._get_client().test_connection()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'title': _("AI Provider"),
                'message': _(
                    "Connection to %(provider)s succeeded.",
                    provider=dict(self._selection_name()).get(
                        self.name, self.name,
                    ),
                ),
                'sticky': False,
            },
        }

    # ----------------------------------------------------------
    # Compute
    # ----------------------------------------------------------

    @api.depends('name')
    def _compute_display_name(self):
        labels = dict(self._fields['name']._description_selection(self.env))
        for record in self:
            record.display_name = labels.get(record.name) or record.name or ''

    @api.depends('name')
    def _compute_capabilities(self):
        for record in self:
            impl = REGISTRY.get(record.name)
            record.supports_web_search = bool(impl and impl.supports_web_search)
            record.supports_image_generation = bool(impl and impl.supports_image_generation)
            record.supports_code_interpreter = bool(impl and impl.supports_code_interpreter)

    # ----------------------------------------------------------
    # Constraints
    # ----------------------------------------------------------

    _sql_constraints = [
        (
            'unique_name',
            'unique(name)',
            "A provider with this name already exists.",
        ),
    ]
