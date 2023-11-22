from odoo import models, fields


class ResCompany(models.Model):
    
    _inherit = 'res.company'
    
    #----------------------------------------------------------
    # Fields
    #----------------------------------------------------------
    
    favicon = fields.Binary(
        string="Company Favicon", 
        attachment=True
    )
    
    background_image_light = fields.Binary(
        string='Apps Menu Background Light Image',
        attachment=True
    )
    
    background_image_dark = fields.Binary(
        string='Apps Menu Background Dark Image',
        attachment=True
    )

