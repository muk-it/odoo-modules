from odoo import fields, models


class ResCompany(models.Model):

    _inherit = 'res.company'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    default_ai_provider_id = fields.Many2one(
        comodel_name='muk_ai.provider',
        string="Default AI Provider",
        domain=[('active', '=', True)],
        help=(
            "Provider used when an agent does not specify one. "
            "Falls back to the first active provider if unset."
        ),
    )

    default_ai_agent_id = fields.Many2one(
        comodel_name='muk_ai.agent',
        string="Default AI Agent",
        domain=[('active', '=', True)],
        help=(
            "Agent used for new chat sessions when the user has not "
            "picked one. Falls back to the first active agent if unset."
        ),
    )
