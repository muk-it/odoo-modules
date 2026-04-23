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
        required=True,
        readonly=True,
    )

    sequence = fields.Integer(
        string="Sequence",
        default=10,
    )

    provider_id = fields.Many2one(
        comodel_name='muk_ai.provider',
        string="Provider",
        required=True,
        readonly=True,
        ondelete='cascade',
    )

    technical_name = fields.Char(
        string="Technical Name",
        required=True,
        readonly=True,
        index=True,
        help="Provider-facing model identifier — e.g. 'gpt-5-mini'.",
    )

    context_window = fields.Integer(
        string="Context Window",
        required=True,
        readonly=True,
        help="Maximum input tokens the provider accepts for this model.",
    )

    input_rate = fields.Float(
        string="Input $/M tokens",
        digits=(12, 6),
        required=True,
        readonly=True,
        help="Cost in USD per 1,000,000 fresh input tokens.",
    )

    output_rate = fields.Float(
        string="Output $/M tokens",
        digits=(12, 6),
        required=True,
        readonly=True,
        help="Cost in USD per 1,000,000 output tokens.",
    )

    cached_rate = fields.Float(
        string="Cached $/M tokens",
        digits=(12, 6),
        default=0.0,
        readonly=True,
        help="Cost in USD per 1,000,000 cached input tokens.",
    )

    currency = fields.Char(
        string="Currency",
        required=True,
        readonly=True,
        default='USD',
        help="ISO code of the price currency.",
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
        input_cost = (
            max(0, input_tokens - cached_tokens) * self.input_rate +
            cached_tokens * (self.cached_rate or self.input_rate)
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

    _unique_provider_model = models.Constraint(
        'unique(provider_id, technical_name)',
        "A model with this provider and name already exists.",
    )

    @api.constrains('context_window')
    def _check_context_window(self):
        for record in self:
            if record.context_window <= 0:
                raise ValidationError(_(
                    "Context Window must be a positive integer.",
                ))
