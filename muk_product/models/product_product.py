from __future__ import annotations

from odoo import api, fields, models
from odoo.fields import Domain


class ProductProduct(models.Model):
    """Add manufacturer codes and automatic references and barcodes."""

    _inherit = 'product.product'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    manufacturer_code = fields.Char(string='Manufacturer Product Code')

    default_code = fields.Char(
        tracking=True,
        copy=False,
    )

    barcode = fields.Char(tracking=True)

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _get_next_default_code(self) -> str | None:
        """Return the next internal reference from its sequence."""
        return self.env['ir.sequence'].next_by_code('product.product.default_code')

    @api.model
    def _get_next_barcode(self) -> str | None:
        """Return the next barcode from its sequence with a checksum digit."""
        code = self.env['ir.sequence'].next_by_code('product.product.barcode')
        if code:
            evensum = sum(int(digit) for digit in code[-2::-2])
            oddsum = sum(int(digit) for digit in code[-1::-2])
            checksum = (10 - ((evensum + oddsum * 3) % 10)) % 10
            return f'{code}{checksum}'
        return code

    def _assign_missing_product_codes(self) -> None:
        """Fill the default code and barcode of variants that still lack one."""
        for record in self:
            vals = {}
            if not record.default_code:
                vals['default_code'] = record._get_next_default_code()
            if not record.barcode:
                vals['barcode'] = record._get_next_barcode()
            if vals:
                record.write(vals)

    # ----------------------------------------------------------
    # Compute
    # ----------------------------------------------------------

    @api.model
    def _search_display_name(self, operator: str, value) -> Domain:
        """Extend the display-name search to also match manufacturer codes."""
        res = super()._search_display_name(operator, value)
        combine = Domain.OR if operator not in Domain.NEGATIVE_OPERATORS else Domain.AND
        return combine([res, [('manufacturer_code', operator, value)]])

    # ----------------------------------------------------------
    # Constraints
    # ----------------------------------------------------------

    _unique_default_code = models.UniqueIndex(
        '(default_code) WHERE default_code IS NOT NULL',
        'Another entry with the same default code already exists.',
    )

    # ----------------------------------------------------------
    # ORM
    # ----------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list: list[dict]) -> ProductProduct:
        """Assign automatic default codes and barcodes when missing."""
        if not self.env.context.get('skip_product_code_automation'):
            for vals in vals_list:
                if not vals.get('default_code', False):
                    vals['default_code'] = self._get_next_default_code()
                if not vals.get('barcode', False):
                    vals['barcode'] = self._get_next_barcode()
        return super().create(vals_list)
