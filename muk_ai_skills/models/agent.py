from odoo import api, models


class AIAgent(models.Model):

    _inherit = 'muk_ai.agent'

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _get_default_essential_tool_names(self):
        return super()._get_default_essential_tool_names() + [
            'invoke_skill', 'read_resource',
        ]
