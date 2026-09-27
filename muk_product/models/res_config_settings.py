from __future__ import annotations

from odoo import api, fields, models
from odoo.exceptions import UserError

PRODUCT_SEQUENCES = {
    'active_product_default_code_automation': 'muk_product.seq_product_reference',
    'active_product_barcode_automation': 'muk_product.seq_product_barcode',
}


class ResConfigSettings(models.TransientModel):
    """Toggle the product reference and barcode sequence automations."""

    _inherit = 'res.config.settings'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    active_product_default_code_automation = fields.Boolean(
        string='Active Product Internal Reference Automation',
    )

    active_product_barcode_automation = fields.Boolean(
        string='Active Product Barcode Automation',
    )

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    def get_values(self) -> dict:
        """Load the sequence automation flags into the settings values."""
        res = super().get_values()
        for field, xmlid in PRODUCT_SEQUENCES.items():
            sequence = self.env.ref(xmlid, False)
            res[field] = bool(sequence and sequence.active)
        return res

    def set_values(self) -> None:
        """Apply the sequence automation flags to their sequences.

        :raise UserError: when a sequence cannot be found
        """
        super().set_values()
        for field, xmlid in PRODUCT_SEQUENCES.items():
            sequence = self.env.ref(xmlid, False)
            if not sequence:
                raise UserError(self.env._("The sequence couldn't be found."))
            sequence.active = self[field]
