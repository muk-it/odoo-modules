from __future__ import annotations

from odoo import api, models
from odoo.http import Request


class WebsitePage(models.Model):
    """Keep the page cache from serving one visitor's consent to another."""

    _inherit = 'website.page'

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    def _get_cache_key(self, request: Request) -> tuple:
        """Add the granular consent state to the page cache key.

        Core keys on ``(website, language, path, debug)``, none of which
        describes what the visitor consented to, yet the page does. The
        configuration signature is in there for the same reason: the key
        describes the request, the response also depends on the registry.

        A visitor who refused everything and one who has not been asked yet
        grant the same set, so whether a decision exists is part of the key too.
        """
        key = super()._get_cache_key(request)
        website = request.website
        if not website or not website._is_cookie_consent_active():
            return key
        categories = ','.join(sorted(website._get_granted_cookie_codes()))
        services = ','.join(sorted(website._get_granted_cookie_services()))
        return (
            *key,
            categories,
            services,
            website._has_cookie_decision(),
            website._get_cookie_lifetime_days(),
            website._get_cookie_render_signature(),
        )
