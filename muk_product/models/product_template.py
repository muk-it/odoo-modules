from __future__ import annotations

from odoo import api, fields, models


class ProductTemplate(models.Model):
    """Expose manufacturer fields and sync the code with the variant."""

    _inherit = 'product.template'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    manufacturer_id = fields.Many2one(
        comodel_name='res.partner',
        string='Manufacturer',
    )

    manufacturer_name = fields.Char(string='Manufacturer Product Name')

    manufacturer_url = fields.Char(string='Manufacturer Product URL')

    manufacturer_code = fields.Char(
        compute='_compute_manufacturer_code',
        inverse='_inverse_manufacturer_code',
        string='Manufacturer Product Code',
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _get_related_fields_variant_template(self) -> list[str]:
        """Add the manufacturer code to the variant-template related fields."""
        res = super()._get_related_fields_variant_template()
        return res + ['manufacturer_code']

    # ----------------------------------------------------------
    # Compute
    # ----------------------------------------------------------

    @api.depends('product_variant_ids.manufacturer_code')
    def _compute_manufacturer_code(self) -> None:
        """Mirror the manufacturer code from the single product variant."""
        self._compute_template_field_from_variant_field('manufacturer_code')

    def _inverse_manufacturer_code(self) -> None:
        """Propagate the manufacturer code back to the product variant."""
        self._set_product_variant_field('manufacturer_code')
