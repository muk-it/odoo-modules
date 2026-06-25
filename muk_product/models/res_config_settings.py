from __future__ import annotations

from odoo import _, api, fields, models
from odoo.exceptions import UserError


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
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _get_product_sequence_active(self, xmlid: str) -> bool:
        """Return whether the sequence referenced by ``xmlid`` is active."""
        sequence = self.env.ref(xmlid, False)
        return sequence.active if sequence else False

    @api.model
    def _set_product_sequence_active(self, xmlid: str, active: bool) -> None:
        """Set the active flag on the sequence referenced by ``xmlid``.

        :raise UserError: when the sequence cannot be found
        """
        sequence = self.env.ref(xmlid, False)
        if not sequence:
            raise UserError(_("The sequence couldn't be found."))
        sequence.write({'active': active})

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    def get_values(self) -> dict:
        """Load the sequence automation flags into the settings values."""
        res = super().get_values()
        res.update(
            {
                'active_product_default_code_automation': (
                    self._get_product_sequence_active(
                        'muk_product.seq_product_reference'
                    )
                ),
                'active_product_barcode_automation': (
                    self._get_product_sequence_active('muk_product.seq_product_barcode')
                ),
            }
        )
        return res

    def set_values(self) -> None:
        """Apply the sequence automation flags to their sequences."""
        res = super().set_values()
        self._set_product_sequence_active(
            'muk_product.seq_product_reference',
            self.active_product_default_code_automation,
        )
        self._set_product_sequence_active(
            'muk_product.seq_product_barcode',
            self.active_product_barcode_automation,
        )
        return res
