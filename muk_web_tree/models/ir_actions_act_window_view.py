from __future__ import annotations

from odoo import fields, models


class IrActionsActWindowView(models.Model):
    """Allow window actions to open the treelist view."""

    _inherit = 'ir.actions.act_window.view'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    view_mode = fields.Selection(
        selection_add=[('treelist', 'Tree List')],
        ondelete={'treelist': 'cascade'},
    )
