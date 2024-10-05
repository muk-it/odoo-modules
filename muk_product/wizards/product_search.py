import ast

from odoo import api, fields, models
from odoo.osv import expression


class ProductSearch(models.TransientModel):
    
    _name = 'muk_product.product_search'
    _description = 'Product Search'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    search_value = fields.Text(
        string="Search",
    )

    value_split_operator = fields.Selection(
        selection=[
            ('\n', 'Enter'),
            (' ', 'Space'),
            (',', 'Comma'),
            (';', 'Semicolon'),
            ('\t', 'Tab'),
        ],
        string="Split by",
        required=True,
        default='\n',
    )

    search_operator = fields.Selection(
        selection=[
            ('=', 'Match'),
            ('ilike', 'Contains'),
        ],
        string="Search with",
        required=True,
        default='=',
    )

    search_field = fields.Selection(
        selection=[
            ('product_variant_ids.default_code', 'Internal Reference'),
            ('name', 'Product Name'),
            ('product_variant_ids.barcode', 'Barcode'),
        ],
        string="Field",
        required=True,
        default='product_variant_ids.default_code',
    )

    search_domain = fields.Text(
        compute='_compute_search_domain',
        string="Domain",
        readonly=False,
        store=True,
    )

    product_preview_ids = fields.One2many(
        compute='_compute_product_preview',
        comodel_name='product.template',
        string="Preview Records",
    )
    
    product_preview_hint = fields.Boolean(
        compute='_compute_product_preview',
        string="Preview Hint",
    )

    action_id = fields.Many2one(
        comodel_name='ir.actions.act_window',
        string="Action",
        required=True,
        domain=[
            ('res_model', '=', 'product.template'), 
            ('type', '=', 'ir.actions.act_window')
        ],
        default=lambda self: self.env.ref('product.product_template_action_all', False)
    )

    # ----------------------------------------------------------
    # Compute
    # ----------------------------------------------------------

    @api.depends(
        'search_value', 
        'value_split_operator', 
        'search_operator', 
        'search_field'
    )
    def _compute_search_domain(self):
        for record in self:
            search_domain = []
            search_value = record.search_value or ''
            search_parts = search_value.split(record.value_split_operator)
            if not search_value:
                search_domain = []
            elif record.search_operator == '=':
                search_domain = [(record.search_field, 'in', search_parts)]
            else:
                search_domain = expression.OR([
                    [(record.search_field, record.search_operator, part)]
                    for part in search_parts
                ])
            record.search_domain = str(search_domain)

    @api.depends('search_domain')
    def _compute_product_preview(self):
        self.product_preview_ids = False
        self.product_preview_hint = False
        for record in self.filtered(
            lambda r: r.search_domain and r.search_domain != '[]'
        ):
            templates = self.env['product.template'].search(
                ast.literal_eval(record.search_domain), limit=8
            )
            record.product_preview_ids = templates[:-1]
            record.product_preview_hint = len(templates) > 7

    # ----------------------------------------------------------
    # Action
    # ----------------------------------------------------------

    def action_search_products(self):
        self.ensure_one()
        action = self.action_id._get_action_dict()
        if self.search_domain:
            action['domain'] = ast.literal_eval(
                self.search_domain
            )
        return action
