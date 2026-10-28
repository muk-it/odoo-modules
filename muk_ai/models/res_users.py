from __future__ import annotations

from odoo import fields, models


class ResUsers(models.Model):
    """Give a user a monthly AI budget of their own."""

    _inherit = 'res.users'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    ai_monthly_budget = fields.Float(
        string='Monthly AI Budget',
        help=(
            'Maximum this user may spend on AI per calendar month, in the '
            'price currency of the models. Set 0 to use the budget per user '
            'from the settings.'
        ),
        digits=(12, 2),
    )
