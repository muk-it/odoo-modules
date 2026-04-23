from odoo import fields, models


class AIProvider(models.Model):

    _inherit = 'muk_ai.provider'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    agentidoo_acting_user_id = fields.Many2one(
        comodel_name='res.users',
        string="Agentidoo Acting User",
        domain=[('share', '=', False), ('active', '=', True)],
        help="Internal user Aimee acts as when running tool calls against Odoo.",
    )

    agentidoo_session_registered = fields.Boolean(
        string="Odoo Instance Registered with Agentidoo",
        default=False,
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _build_request_extra(self):
        extra = super()._build_request_extra()
        if self.name == 'agentidoo':
            extra['bag'] = self.env.context.get('agentidoo_bag')
        return extra
