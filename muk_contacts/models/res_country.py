from odoo import models, fields, api, _


class Country(models.Model):

    _inherit = 'res.country'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------
    
    partner_properties_definition = fields.PropertiesDefinition(
        string='Partner Properties'
    )
