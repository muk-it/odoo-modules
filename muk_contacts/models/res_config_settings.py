from __future__ import annotations

from odoo import api, fields, models
from odoo.exceptions import UserError


class ResConfigSettings(models.TransientModel):
    """Toggle the contact number sequence from the settings panel."""

    _inherit = 'res.config.settings'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    active_contact_number_automation = fields.Boolean(
        string='Active Contact Number Automation',
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _get_contact_number_sequence(self) -> models.Model:
        """Return the contact number sequence.

        :raise UserError: when the contact number sequence cannot be found
        """
        sequence = self.env.ref('muk_contacts.sequence_contact_number', False)
        if not sequence:
            raise UserError(
                self.env._("The contact number sequence couldn't be found.")
            )
        return sequence

    # ----------------------------------------------------------
    # Actions
    # ----------------------------------------------------------

    def action_open_contact_number_sequence(self) -> dict:
        """Open the form of the contact number sequence."""
        return self._get_contact_number_sequence().get_record_default_action()

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    def get_values(self) -> dict:
        """Read the contact number automation flag from the sequence state."""
        res = super().get_values()
        sequence = self.env.ref('muk_contacts.sequence_contact_number', False)
        res['active_contact_number_automation'] = bool(sequence and sequence.active)
        return res

    def set_values(self) -> None:
        """Persist the contact number automation flag onto the sequence."""
        res = super().set_values()
        self._get_contact_number_sequence().write(
            {'active': self.active_contact_number_automation}
        )
        return res
