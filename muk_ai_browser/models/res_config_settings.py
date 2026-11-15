from __future__ import annotations

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    """Configure how the assistant behaves in paired browsers."""

    _inherit = 'res.config.settings'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    browser_default_mode = fields.Selection(
        selection=[
            ('allow', 'Allow'),
            ('ask', 'Ask'),
            ('block', 'Block'),
        ],
        string='Browser Default Mode',
        help='What the assistant may do on a site no rule covers.',
        config_parameter='muk_ai_browser.default_mode',
        default='ask',
    )

    browser_pairing_ttl = fields.Integer(
        string='Browser Pairing Code Lifetime',
        help='Seconds a pairing code stays valid.',
        config_parameter='muk_ai_browser.pairing_ttl',
        default=300,
    )
