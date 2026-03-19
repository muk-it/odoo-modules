from odoo import fields, models


class ResConfigSettings(models.TransientModel):

    _inherit = 'res.config.settings'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    preview_office_enabled = fields.Boolean(
        config_parameter='muk_web_preview.office_enabled',
        string='MS Office Preview',
        help=(
            'Enable preview of Microsoft Office files (docx, xlsx, pptx) '
            'using the Microsoft Office Online viewer. This requires the '
            'Odoo instance to be publicly accessible from the internet. '
            'Files are served via a short-lived one-time token URL.'
        ),
    )
