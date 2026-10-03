from __future__ import annotations

from odoo import api, models
from odoo.http.requestlib import Request


class WebsitePage(models.Model):
    """Keep the page cache from serving one visitor's consent to another."""

    _inherit = 'website.page'

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    def _get_cache_key(self, request: Request) -> tuple:
        """Add the granular consent state to the page cache key.

        Also the decision itself, since a refusal and no answer grant the same
        set, and the configuration signature the response depends on.
        """
        key = super()._get_cache_key(request)
        website = self.env.website
        if not website or not website._is_cookie_consent_active():
            return key
        return (
            *key,
            website._get_cookie_consent_key(),
            website._has_cookie_decision(),
            website._get_cookie_lifetime_days(),
            website._get_cookie_render_signature(),
        )
