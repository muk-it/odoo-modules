import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


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
        value = (
            sequence_contact_number.active
            if sequence_contact_number
            else False
        )
        _logger.warning(
            "DEBUG_CONTACT_NUMBER: get_values() sequence=%s, active=%s, returning=%s",
            sequence_contact_number, 
            sequence_contact_number.active if sequence_contact_number else 'N/A',
            value,
        )
        res.update({
            'active_contact_number_automation': value
        })
        return res

    def set_values(self):
        sequence_contact_number = self.env.ref(
            'muk_contacts.sequence_contact_number', False
        )
        _logger.warning(
            "DEBUG_CONTACT_NUMBER: set_values() called. "
            "self.active_contact_number_automation=%s, "
            "sequence=%s, sequence.active=%s (before write)",
            self.active_contact_number_automation,
            sequence_contact_number,
            sequence_contact_number.active if sequence_contact_number else 'N/A',
        )
        res = super().set_values()
        if not sequence_contact_number:
            raise UserError(_(
                "The contact number sequence couldn't be found."
            ))
        sequence_contact_number.write({
            'active': self.active_contact_number_automation
        })
        _logger.warning(
            "DEBUG_CONTACT_NUMBER: set_values() wrote active=%s to sequence. "
            "sequence.active is now=%s",
            self.active_contact_number_automation,
            sequence_contact_number.active,
        )
        return res
