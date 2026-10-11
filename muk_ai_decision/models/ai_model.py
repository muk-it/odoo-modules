from odoo import fields, models


class AIModel(models.Model):
    """Add the decision modality to the model catalogue."""

    _inherit = 'muk_ai.model'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    modality = fields.Selection(
        selection_add=[('decision', 'Decision')],
        ondelete={'decision': 'cascade'},
    )
