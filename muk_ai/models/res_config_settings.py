from odoo import fields, models


class ResConfigSettings(models.TransientModel):

    _inherit = 'res.config.settings'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    ai_provider_id = fields.Many2one(
        related='company_id.default_ai_provider_id',
        readonly=False,
    )

    ai_agent_id = fields.Many2one(
        related='company_id.default_ai_agent_id',
        readonly=False,
    )
