from odoo import fields, models


class MailMessage(models.Model):

    _inherit = 'mail.message'

    muk_ai_session_id = fields.Many2one(
        comodel_name='muk_ai.session',
        string="MuK AI Session",
        index='btree_not_null',
        ondelete='cascade',
    )
