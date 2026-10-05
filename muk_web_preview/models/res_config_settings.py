from __future__ import annotations

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    """Add the Office preview setting to the general settings."""

    _inherit = 'res.config.settings'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    preview_office_enabled = fields.Boolean(
        config_parameter='muk_web_preview.office_enabled',
        string='MS Office Preview',
        help=(
            'Preview Word, Excel and PowerPoint files with the Microsoft Office '
            'Online viewer. Microsoft downloads the file through a signed link '
            'that expires after five minutes, so the database must be reachable '
            'from the internet.'
        ),
    )
