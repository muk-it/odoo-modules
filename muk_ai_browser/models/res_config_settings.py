from __future__ import annotations

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    """Add browser pairing and safety settings to the configuration."""

    _inherit = 'res.config.settings'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    browser_extension_id = fields.Char(
        string='Browser Extension ID',
        config_parameter='muk_ai_browser.extension_id',
        help='Chrome extension id allowed to pair with this Odoo instance.',
    )

    browser_pairing_ttl = fields.Integer(
        string='Pairing Code TTL (seconds)',
        config_parameter='muk_ai_browser.pairing_ttl',
        default=120,
        help='Lifetime of a one-time pairing code before it expires.',
    )

    browser_risky_keywords = fields.Char(
        string='Risky Keywords',
        config_parameter='muk_ai_browser.risky_keywords',
        default='checkout,pay,buy,order,delete',
        help=(
            'Comma-separated keywords that force an approval gate on a browser '
            'action targeting a matching element or URL.'
        ),
    )
