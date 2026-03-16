from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):

    _inherit = 'res.config.settings'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    llms_txt_enabled = fields.Boolean(
        related='website_id.llms_txt_enabled',
        readonly=False,
    )

    llms_markdown_enabled = fields.Boolean(
        related='website_id.llms_markdown_enabled',
        readonly=False,
    )

    llms_full_txt_enabled = fields.Boolean(
        related='website_id.llms_full_txt_enabled',
        readonly=False,
    )

    llms_content_signal = fields.Selection(
        related='website_id.llms_content_signal',
        readonly=False,
    )

    llms_include_blogs = fields.Boolean(
        related='website_id.llms_include_blogs',
        readonly=False,
    )

    llms_include_products = fields.Boolean(
        related='website_id.llms_include_products',
        readonly=False,
    )

    llms_include_events = fields.Boolean(
        related='website_id.llms_include_events',
        readonly=False,
    )
