from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AIModel(models.Model):

    _name = 'muk_ai.model'
    _description = "AI Model"
    _order = 'sequence, provider_id, name'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    name = fields.Char(
        string="Label",
        readonly=True,
        required=True,
    )

    sequence = fields.Integer(
        string="Sequence",
        default=10,
    )

    provider_id = fields.Many2one(
        comodel_name='muk_ai.provider',
        string="Provider",
        readonly=True,
        required=True,
        ondelete='cascade',
    )

    technical_name = fields.Char(
        string="Technical Name",
        help="Provider-facing model identifier — e.g. 'gpt-5-mini'.",
        readonly=True,
        required=True,
        index=True,
    )

    context_window = fields.Integer(
        string="Context Window",
        help="Maximum input tokens the provider accepts for this model.",
        readonly=True,
        required=True,
    )

    input_rate = fields.Float(
        string="Input $/M tokens",
        help="Cost in USD per 1,000,000 fresh input tokens.",
        readonly=True,
        required=True,
        digits=(12, 6),
    )

    output_rate = fields.Float(
        string="Output $/M tokens",
        help="Cost in USD per 1,000,000 output tokens.",
        readonly=True,
        required=True,
        digits=(12, 6),
    )

    cached_rate = fields.Float(
        string="Cached $/M tokens",
        help=(
            "Cost in USD per 1,000,000 cached input tokens. "
            "Leave at 0 when the provider does not bill cached tokens "
            "separately — the input rate is then used as the fallback."
        ),
        readonly=True,
        default=0.0,
        digits=(12, 6),
    )

    currency = fields.Char(
        string="Currency",
        help="ISO code of the price currency.",
        readonly=True,
        required=True,
        default='USD',
    )

    active = fields.Boolean(
        string="Active",
        default=True,
    )

    notes = fields.Text(
        string="Notes",
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _compute_usage_cost(self, usage):
        input_tokens = int((usage or {}).get('input_tokens') or 0)
        output_tokens = int((usage or {}).get('output_tokens') or 0)
        cached_tokens = int((usage or {}).get('cached_tokens') or 0)
        cached_rate = self.cached_rate if self.cached_rate > 0 else self.input_rate
        input_cost = (
            max(0, input_tokens - cached_tokens) * self.input_rate +
            cached_tokens * cached_rate
        )
        output_cost = (output_tokens * self.output_rate)
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
            "A model with this provider and name already exists.",
        ),
    ]

    @api.constrains('context_window')
    def _check_context_window(self):
        for record in self:
            if record.context_window <= 0:
                raise ValidationError(_(
                    "Context Window must be a positive integer.",
                ))
