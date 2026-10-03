from __future__ import annotations

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    """Expose the cookie consent settings on the website configuration screen."""

    _inherit = 'res.config.settings'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    cookie_policy_version = fields.Integer(
        related='website_id.cookie_policy_version',
        readonly=False,
    )

    cookie_consent_mode = fields.Selection(
        related='website_id.cookie_consent_mode',
        readonly=False,
    )

    cookie_scan_date = fields.Datetime(
        related='website_id.cookie_scan_date',
    )

    # ----------------------------------------------------------
    # Actions
    # ----------------------------------------------------------

    def action_cookie_scan(self) -> dict:
        """Scan the website these settings belong to."""
        self.ensure_one()
        return self.website_id.action_cookie_scan()
