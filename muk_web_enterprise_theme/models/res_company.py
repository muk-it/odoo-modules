from __future__ import annotations

from odoo import fields, models


class ResCompany(models.Model):
    """Add favicon and apps menu background image fields to the company."""

    _inherit = 'res.company'
    _explanation = (
        'Companies also store the browser favicon and the light and dark background '
        'images of the apps menu.'
    )

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    favicon = fields.Binary(
        string='Company Favicon',
        attachment=True,
    )

    background_image_light = fields.Binary(
        string='Apps Menu Background Light Image',
        attachment=True,
    )

    background_image_dark = fields.Binary(
        string='Apps Menu Background Dark Image',
        attachment=True,
    )
