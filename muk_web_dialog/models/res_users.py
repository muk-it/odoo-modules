from __future__ import annotations

from odoo import fields, models


class ResUsers(models.Model):
    """Store the per-user dialog size preference."""

    _inherit = 'res.users'
    _explanation = 'Users also choose whether dialogs open in normal size or maximized.'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    dialog_size = fields.Selection(
        selection=[
            ('minimize', 'Minimize'),
            ('maximize', 'Maximize'),
        ],
        string='Dialog Size',
        default='minimize',
        required=True,
        user_writeable=True,
    )
