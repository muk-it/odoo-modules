from __future__ import annotations

import ast

from odoo import api, fields, models
from odoo.fields import Domain


class ProductSearch(models.TransientModel):
    """Bulk-search products from a list of values and open the result."""

    _name = 'muk_product.product_search'
    _description = 'Product Search'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    search_value = fields.Text(
        string='Search',
    )

    value_split_operator = fields.Selection(
        selection=[
            ('\n', 'Enter'),
            (' ', 'Space'),
            (',', 'Comma'),
            (';', 'Semicolon'),
            ('\t', 'Tab'),
        ],
        string='Split by',
        required=True,
        default='\n',
    )

    search_operator = fields.Selection(
        selection=[
            ('=', 'Match'),
            ('ilike', 'Contains'),
        ],
        string='Search with',
        required=True,
        default='=',
    )

    search_field = fields.Selection(
        selection=[
            ('product_variant_ids.default_code', 'Internal Reference'),
            ('name', 'Product Name'),
            ('product_variant_ids.barcode', 'Barcode'),
        ],
        string='Field',
        required=True,
        default='product_variant_ids.default_code',
    )

    search_domain = fields.Text(
        compute='_compute_search_domain',
        string='Domain',
        readonly=False,
        store=True,
    )

    product_preview_ids = fields.One2many(
        compute='_compute_product_preview',
        comodel_name='product.template',
        string='Preview Records',
    )

    product_preview_hint = fields.Boolean(
        compute='_compute_product_preview',
        string='Preview Hint',
    )

    action_id = fields.Many2one(
        comodel_name='ir.actions.act_window',
        string='Action',
        required=True,
        domain=[('res_model', '=', 'product.template')],
        default=lambda self: self.env.ref('product.product_template_action_all', False),
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _get_search_values(self) -> list[str]:
        """Return the non-blank search values split by the configured separator."""
        parts = (self.search_value or '').split(self.value_split_operator)
        return [value for value in (part.strip() for part in parts) if value]

    # ----------------------------------------------------------
    # Compute
    # ----------------------------------------------------------

    @api.depends(
        'search_value',
        'value_split_operator',
        'search_operator',
        'search_field',
    )
    def _compute_search_domain(self) -> None:
        """Build the search domain from the split values and operator."""
        for record in self:
            search_domain = []
            search_parts = record._get_search_values()
            if search_parts and record.search_operator == '=':
                search_domain = [(record.search_field, 'in', search_parts)]
            elif search_parts:
                search_domain = Domain.OR(
                    [
                        [(record.search_field, record.search_operator, part)]
                        for part in search_parts
                    ]
                )
            record.search_domain = repr(search_domain)

    @api.depends('search_domain')
    def _compute_product_preview(self) -> None:
        """Preview up to seven matching templates and flag any overflow."""
        self.product_preview_ids = False
        self.product_preview_hint = False
        for record in self.filtered(
            lambda r: r.search_domain and r.search_domain != '[]'
        ):
            templates = self.env['product.template'].search(
                ast.literal_eval(record.search_domain), limit=8
            )
            record.product_preview_ids = templates[:7]
            record.product_preview_hint = len(templates) > 7

    # ----------------------------------------------------------
    # Action
    # ----------------------------------------------------------

    def action_search_products(self) -> dict:
        """Return the configured action filtered by the computed domain."""
        self.ensure_one()
        action = self.action_id._get_action_dict()
        action['domain'] = ast.literal_eval(self.search_domain or '[]')
        return action
