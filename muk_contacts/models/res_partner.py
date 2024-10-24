from odoo import models, fields, api, _
from odoo.tools import SQL


class Partner(models.Model):

    _inherit = 'res.partner'
    _rec_names_search = [
        'complete_name',
        'email',
        'ref',
        'vat',
        'company_registry',
        'contact_number'
    ]
    
    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------
    
    contact_number = fields.Char(
        string="Contact Number",
        tracking=True,
        copy=False,
    )

    partner_properties = fields.Properties(
        string='Properties', 
        definition='country_id.partner_properties_definition', 
        copy=True
    )

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------
    
    def init(self):
        self.env.cr.execute(
            SQL(
                """
                    CREATE UNIQUE INDEX IF NOT EXISTS res_partner_unique_contact_number 
                    ON %s (contact_number) 
                    WHERE contact_number IS NOT NULL AND parent_id IS NULL
                """,
                SQL.identifier(self._table)
            )
        )
        
    #----------------------------------------------------------
    # Helper
    #----------------------------------------------------------
    
    @api.model
    def _commercial_fields(self):
        return super()._commercial_fields() + [
            'contact_number'
        ]

    @api.model
    def _get_next_contact_number(self):
        return self.env['ir.sequence'].next_by_code(
            'contact.number'
        )

    #----------------------------------------------------------
    # Actions
    #----------------------------------------------------------
    
    def action_view_partner(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'name': self.name,
            'res_model': 'res.partner',
            'res_id': self.id,
            'views': [(self.env.ref('base.view_partner_form').id, 'form')],
            'context': self.env.context
        }
        
    def action_generate_contact_number(self):
        self.ensure_one()
        self.write({
            'contact_number': self._get_next_contact_number()
        })
    
    #----------------------------------------------------------
    # Compute
    #----------------------------------------------------------

    @api.depends('contact_number')
    @api.depends_context('show_contact_number')
    def _compute_display_name(self):
        super()._compute_display_name()
        if self.env.context.get('show_contact_number'):
            for record in self.filtered('contact_number'):
                record.display_name = f"[{record.contact_number}] {record.display_name}"

    #----------------------------------------------------------
    # ORM
    #----------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if (
                not vals.get('contact_number', False) and 
                not vals.get('parent_id', False)
            ):
                vals['contact_number'] = self._get_next_contact_number()
        return super().create(vals_list)
