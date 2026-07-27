from __future__ import annotations

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.muk_ai.tools import REASONING_EFFORT_SELECTION


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
        help="Provider-facing model identifier — e.g. 'gpt-5-mini'.",
        readonly=True,
        required=True,
        index=True,
    )

    context_window = fields.Integer(
        string='Context Window',
        help='Maximum input tokens the provider accepts for this model.',
        readonly=True,
        required=True,
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

    input_rate = fields.Float(
        string='Input $/M tokens',
        help='Cost in USD per 1,000,000 fresh input tokens.',
        readonly=True,
        required=True,
        digits=(12, 6),
    )

    output_rate = fields.Float(
        string='Output $/M tokens',
        help='Cost in USD per 1,000,000 output tokens.',
        readonly=True,
        required=True,
        digits=(12, 6),
    )

    cache_read_rate = fields.Float(
        string='Cache Read $/M tokens',
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
        string='Cache Write $/M tokens',
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

    def _compute_usage_cost(self, usage: dict | None) -> dict:
        """Return input, output, and total cost for a token usage payload.

        ``input_tokens`` is the full prompt; cache-read and cache-write
        tokens are subsets of it billed at their own rates, with the fresh
        input rate as the fallback when a cache rate is unset.
        """
        usage = usage or {}
        input_tokens = int(usage.get('input_tokens') or 0)
        output_tokens = int(usage.get('output_tokens') or 0)
        cache_read_tokens = int(usage.get('cache_read_tokens') or 0)
        cache_write_tokens = int(usage.get('cache_write_tokens') or 0)
        cache_read_rate = self.cache_read_rate or self.input_rate
        cache_write_rate = self.cache_write_rate or self.input_rate
        fresh_tokens = max(0, input_tokens - cache_read_tokens - cache_write_tokens)
        input_cost = (
            fresh_tokens * self.input_rate
            + cache_read_tokens * cache_read_rate
            + cache_write_tokens * cache_write_rate
        )
        output_cost = output_tokens * self.output_rate
        return {
            'input_cost': input_cost / 1_000_000,
            'output_cost': output_cost / 1_000_000,
            'total_cost': (input_cost + output_cost) / 1_000_000,
        }

    # ----------------------------------------------------------
    # Constraints
    # ----------------------------------------------------------

    _sql_constraints = [
        (
            'unique_provider_model',
            'unique(provider_id, technical_name)',
            'A model with this provider and name already exists.',
        ),
    ]

    @api.constrains('context_window')
    def _check_context_window(self) -> None:
        """Ensure the context window is a positive integer.

        :raise ValidationError: when the context window is not positive
        """
        for record in self:
            if record.context_window <= 0:
                raise ValidationError(
                    _(
                        'Context Window must be a positive integer.',
                    )
                )
