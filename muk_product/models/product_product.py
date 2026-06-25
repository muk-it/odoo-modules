from __future__ import annotations

from functools import reduce

from odoo import api, fields, models
from odoo.fields import Domain
from odoo.tools import format_amount


class ProductProduct(models.Model):
    """Add manufacturer codes, automatic references, and price strings."""

    _inherit = 'product.product'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    fixed_price = fields.Float(
        string='Variant Price',
        digits='Product Price',
    )

    price_string = fields.Char(compute='_compute_price_string')

    manufacturer_code = fields.Char(string='Manufacturer Product Code')

    # ----------------------------------------------------------
    # Override Fields
    # ----------------------------------------------------------

    default_code = fields.Char(
        tracking=True,
        copy=False,
    )

    barcode = fields.Char(
        tracking=True,
        copy=False,
    )

    # ----------------------------------------------------------
    # Index
    # ----------------------------------------------------------

    _unique_default_code = models.UniqueIndex(
        '(default_code) WHERE default_code IS NOT NULL',
        'Another entry with the same default code already exists.',
    )

    _unique_barcode = models.UniqueIndex(
        '(barcode) WHERE barcode IS NOT NULL',
        'Another entry with the same barcode already exists.',
    )

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
            evensum = reduce(lambda x, y: int(x) + int(y), code[-2::-2])
            oddsum = reduce(lambda x, y: int(x) + int(y), code[-1::-2])
            checksum = (10 - ((evensum + oddsum * 3) % 10)) % 10
            return f'{code}{checksum}'
        return code

    @api.model
    def _construct_price_string(self, currency, price: float, extra: float) -> str:
        """Format the list price and extra into a human-readable string."""
        joined = [
            format_amount(self.env, price, currency),
            format_amount(self.env, extra, currency),
        ]
        return f'(= {" + ".join(joined)})'

    # ----------------------------------------------------------
    # Compute
    # ----------------------------------------------------------

    @api.model
    def _search_display_name(self, operator: str, value) -> Domain:
        """Extend the display-name search to also match manufacturer codes."""
        res = super()._search_display_name(operator, value)
        combine = Domain.OR if operator not in Domain.NEGATIVE_OPERATORS else Domain.AND
        return combine([res, [('manufacturer_code', operator, value)]])

    @api.depends('fixed_price')
    def _compute_product_price_extra(self) -> None:
        """Derive the price extra from the fixed variant price when set."""
        super()._compute_product_price_extra()
        for record in self.filtered('fixed_price'):
            record.price_extra = record.fixed_price - record.list_price

    @api.depends('currency_id', 'list_price', 'price_extra')
    @api.depends_context('company')
    def _compute_price_string(self) -> None:
        """Compute the formatted price breakdown string per variant."""
        for record in self:
            record.price_string = record._construct_price_string(
                record.currency_id, record.list_price, record.price_extra
            )

    # ----------------------------------------------------------
    # ORM
    # ----------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list: list[dict]) -> ProductProduct:
        """Assign automatic default codes and barcodes when missing."""
        for vals in vals_list:
            if not vals.get('default_code', False):
                vals['default_code'] = self._get_next_default_code()
            if not vals.get('barcode', False):
                vals['barcode'] = self._get_next_barcode()
        return super().create(vals_list)
