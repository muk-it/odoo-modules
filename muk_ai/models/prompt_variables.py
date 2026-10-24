from __future__ import annotations

from odoo import api, fields, models


class AIPromptVariables(models.AbstractModel):
    """Describe the variables of an agent system prompt for the field picker."""

    _name = 'muk_ai.prompt.variables'
    _description = 'AI Prompt Variables'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    user = fields.Many2one(
        comodel_name='res.users',
        string='User',
        help='The user of the chat.',
    )

    company = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        help='The current company of the chat.',
    )

    odoo_version = fields.Char(
        string='Odoo Version',
        help='The full Odoo release, for example 18.0+e.',
    )

    odoo_series = fields.Char(
        string='Odoo Series',
        help='The Odoo series, for example 18.0.',
    )

    # ----------------------------------------------------------
    # ORM
    # ----------------------------------------------------------

    @api.model
    def fields_get(
        self, allfields: list[str] | None = None, attributes: list[str] | None = None
    ) -> dict:
        """Describe the variables only, without the fields every model has."""
        described = super().fields_get(allfields, attributes)
        return {
            name: value
            for name, value in described.items()
            if name not in ('id', 'display_name')
        }
