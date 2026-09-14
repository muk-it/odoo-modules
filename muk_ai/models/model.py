from __future__ import annotations

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.muk_ai.tools import MODALITIES, REASONING_EFFORT_SELECTION


class AIModel(models.Model):
    """LLM model catalogue entry with context window and pricing."""

    _name = 'muk_ai.model'
    _description = 'AI Model'
    _order = 'sequence, provider_id, name'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    name = fields.Char(
        string='Label',
        readonly=True,
        required=True,
    )

    sequence = fields.Integer(
        string='Sequence',
        default=10,
    )

    provider_id = fields.Many2one(
        comodel_name='muk_ai.provider',
        string='Provider',
        readonly=True,
        required=True,
        ondelete='cascade',
    )

    technical_name = fields.Char(
        string='Technical Name',
        help="Provider-facing model identifier — e.g. 'gpt-5.6-terra'.",
        readonly=True,
        required=True,
        index=True,
    )

    modality = fields.Selection(
        selection=[('chat', 'Chat'), ('image', 'Image')],
        string='Modality',
        help=(
            'Kind of work the model does. Decides which rates apply and how '
            'usage is billed; the same technical name may be catalogued once '
            'per modality when the provider prices them apart.'
        ),
        readonly=True,
        required=True,
        default='chat',
    )

    context_window = fields.Integer(
        string='Context Window',
        help='Maximum input tokens the provider accepts for this model.',
        readonly=True,
    )

    reasoning_efforts = fields.Json(
        string='Supported Reasoning Efforts',
        help=(
            'List of reasoning effort tiers this model accepts, e.g. '
            '["low", "medium", "high"]. Leave empty when the model has no '
            'effort control — agents then hide the setting entirely.'
        ),
    )

    reasoning_effort_default = fields.Selection(
        selection=REASONING_EFFORT_SELECTION,
        string='Default Reasoning Effort',
        help=(
            'Tier applied when an agent leaves its reasoning effort on '
            '"Model Default". Empty sends no effort and lets the provider '
            'pick its own default.'
        ),
    )

    rate_unit = fields.Char(
        compute='_compute_rate_unit',
        string='Rate Unit',
    )

    input_rate = fields.Float(
        string='Input Rate',
        help='Cost of fresh input, quoted in the rate unit.',
        readonly=True,
        required=True,
        digits=(12, 6),
    )

    output_rate = fields.Float(
        string='Output Rate',
        help='Cost of output, quoted in the rate unit.',
        readonly=True,
        digits=(12, 6),
    )

    cache_read_rate = fields.Float(
        string='Cache Read Rate',
        help=(
            'Cost in USD per 1,000,000 cache-read input tokens. '
            'Leave at 0 when the provider does not bill cached tokens '
            'separately — the input rate is then used as the fallback.'
        ),
        readonly=True,
        default=0.0,
        digits=(12, 6),
    )

    cache_write_rate = fields.Float(
        string='Cache Write Rate',
        help=(
            'Cost in USD per 1,000,000 cache-write input tokens. '
            'Leave at 0 when the provider does not bill cache writes '
            'separately — the input rate is then used as the fallback.'
        ),
        readonly=True,
        default=0.0,
        digits=(12, 6),
    )

    currency = fields.Char(
        string='Currency',
        help='ISO code of the price currency.',
        readonly=True,
        required=True,
        default='USD',
    )

    active = fields.Boolean(
        string='Active',
        default=True,
    )

    notes = fields.Text(
        string='Notes',
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _default_for(
        self,
        modality: str,
        first: models.BaseModel | None = None,
        configured: bool = True,
    ) -> AIModel:
        """Return the default model of the modality across the active providers.

        The walk is ``first``, the company default, then active providers by sequence.

        :param configured: pass ``False`` to walk accounts that cannot serve too
        """
        providers = self.env['muk_ai.provider']
        chain = (first or providers) | providers._get_default()
        for provider in chain | providers.search([('active', '=', True)]):
            record = provider._default_model(modality)
            if record and (not configured or provider._can_serve()):
                return record
        return self.browse()

    def _compute_usage_cost(self, usage: dict | None) -> dict:
        """Return input, output, and total cost for a provider usage payload."""
        profile = MODALITIES.get(self.modality)
        input_cost, output_cost = (
            profile.cost(self, usage or {}) if profile else (0.0, 0.0)
        )
        return {
            'input_cost': input_cost,
            'output_cost': output_cost,
            'total_cost': input_cost + output_cost,
        }

    # ----------------------------------------------------------
    # Compute
    # ----------------------------------------------------------

    @api.depends('name', 'provider_id.name', 'provider_id.code')
    def _compute_display_name(self) -> None:
        """Suffix the label with the provider, since pickers span every vendor."""
        for record in self:
            record.display_name = f'{record.name} ({record.provider_id.display_name})'

    @api.depends('modality', 'currency')
    def _compute_rate_unit(self) -> None:
        """Spell out the unit the rates are quoted in, e.g. ``USD per M tokens``."""
        for record in self:
            profile = MODALITIES.get(record.modality)
            record.rate_unit = f'{record.currency} {profile.unit}' if profile else ''

    # ----------------------------------------------------------
    # Constraints
    # ----------------------------------------------------------

    _sql_constraints = [
        (
            'unique_provider_model',
            'unique(provider_id, technical_name, modality)',
            'A model with this provider, name and modality already exists.',
        ),
    ]

    @api.constrains('context_window', 'modality')
    def _check_context_window(self) -> None:
        """Ensure a chat model declares a positive context window.

        :raise ValidationError: when a chat model's context window is not positive
        """
        for record in self:
            if record.modality == 'chat' and record.context_window <= 0:
                raise ValidationError(
                    _(
                        'Context Window must be a positive integer.',
                    )
                )
