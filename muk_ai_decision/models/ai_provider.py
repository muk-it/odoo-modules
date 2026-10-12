from __future__ import annotations

from odoo import fields, models

from odoo.addons.muk_ai_decision.providers import REGISTRY, LLMDecisionProvider
from odoo.addons.muk_ai_decision.providers.base import DecisionProviderBase


class AIProvider(models.Model):
    """Add the default decision model and the decision adapter to a provider account."""

    _inherit = 'muk_ai.provider'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    default_decision_model_id = fields.Many2one(
        comodel_name='muk_ai.model',
        string='Default Decision Model',
        help=(
            'Model that answers decisions when the caller pins none. Decision '
            'providers are tried first, then the chat providers, each in list '
            'order, the next one taking over when one fails.'
        ),
        domain="[('provider_id', '=', id), ('modality', '=', 'decision')]",
    )

    decision_parallel = fields.Integer(
        string='Parallel Decisions',
        help=(
            'Decisions about several records sent to this provider at once. '
            'Lower it for a self-hosted server on a CPU, which answers one at '
            'a time and refuses the rest.'
        ),
        required=True,
        default=4,
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _get_decision_client(self) -> DecisionProviderBase:
        """Instantiate the decision adapter, a chat model's structured output by default."""
        return REGISTRY.get(self.name, LLMDecisionProvider)(provider=self)
