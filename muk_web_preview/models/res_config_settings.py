from __future__ import annotations

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    """Add the preview settings to the general settings."""

    _inherit = 'res.config.settings'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    preview_office_enabled = fields.Boolean(
        string='MS Office Preview',
        help=(
            'Preview Word, Excel and PowerPoint files with the Microsoft Office '
            'Online viewer. Microsoft downloads the file through a signed link '
            'that expires after five minutes, so the database must be reachable '
            'from the internet.'
        ),
        config_parameter='muk_web_preview.office_enabled',
    )

    preview_report_open = fields.Boolean(
        string='Open Downloaded Reports',
        help=(
            'Open every downloaded PDF or text report in a new browser tab as '
            'well. The browser must allow pop-ups for the database.'
        ),
        config_parameter='muk_web_preview.report_open',
    )
