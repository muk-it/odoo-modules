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

    cookie_blocking = fields.Boolean(
        related='website_id.cookie_blocking',
        readonly=False,
    )

    cookie_respect_gpc = fields.Boolean(
        related='website_id.cookie_respect_gpc',
        readonly=False,
    )

    cookie_publish_gpc_json = fields.Boolean(
        related='website_id.cookie_publish_gpc_json',
        readonly=False,
    )

    cookie_consent_mode = fields.Selection(
        related='website_id.cookie_consent_mode',
        readonly=False,
    )

    cookie_log_consent = fields.Boolean(
        related='website_id.cookie_log_consent',
        readonly=False,
    )

    cookie_log_ip = fields.Boolean(
        related='website_id.cookie_log_ip',
        readonly=False,
    )

    cookie_policy_url = fields.Char(
        related='website_id.cookie_policy_url',
        readonly=False,
    )
