from odoo import models
from odoo.http import request
from odoo.tools import str2bool


class IrHttp(models.AbstractModel):

    _inherit = 'ir.http'

    #----------------------------------------------------------
    # Functions
    #----------------------------------------------------------
    
    def session_info(self):
        result = super(IrHttp, self).session_info()
        result['disable_quick_create'] = str2bool(
            self.env['ir.config_parameter'].sudo().get_param(
                'muk_web_utils.disable_quick_create', default=''
            ),
            default=False
        )
        return result
