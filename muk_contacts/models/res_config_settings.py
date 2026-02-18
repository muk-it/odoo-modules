from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ResConfigSettings(models.TransientModel):

    _inherit = 'res.config.settings'

    #----------------------------------------------------------
    # Fields
    #----------------------------------------------------------

    active_contact_number_automation = fields.Boolean(
        string="Active Contact Number Automation",
    )

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    def get_values(self):
        res = super().get_values()
        sequence_contact_number = self.env.ref(
            'muk_contacts.sequence_contact_number', False
        )
        res.update({
            'active_contact_number_automation': (
                sequence_contact_number.active
                if sequence_contact_number
                else False
            )
        })
        return res

    def set_values(self):
        res = super().set_values()
        sequence_contact_number = self.env.ref(
            'muk_contacts.sequence_contact_number', False
        )
        if not sequence_contact_number:
            raise UserError(_(
                "The contact number sequence couldn't be found."
            ))
        sequence_contact_number.write({
            'active': self.active_contact_number_automation
        })
        return res
