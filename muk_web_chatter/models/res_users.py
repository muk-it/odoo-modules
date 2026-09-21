from __future__ import annotations

from odoo import fields, models


class ResUsers(models.Model):
    """Add a per-user preference for the chatter position."""

    _inherit = 'res.users'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    chatter_position = fields.Selection(
        selection=[
            ('side', 'Side'),
            ('bottom', 'Bottom'),
        ],
        string='Chatter Position',
        default='side',
        required=True,
        user_writeable=True,
    )
