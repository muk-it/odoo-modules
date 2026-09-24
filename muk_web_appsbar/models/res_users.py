from __future__ import annotations

from odoo import fields, models


class ResUsers(models.Model):
    """Add the per-user sidebar display preference."""

    _inherit = 'res.users'
    _explanation = (
        'Users also choose how the apps sidebar is shown: large, small or invisible.'
    )

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    sidebar_type = fields.Selection(
        selection=[
            ('invisible', 'Invisible'),
            ('small', 'Small'),
            ('large', 'Large'),
        ],
        string='Sidebar Type',
        default='large',
        required=True,
        user_writeable=True,
    )
