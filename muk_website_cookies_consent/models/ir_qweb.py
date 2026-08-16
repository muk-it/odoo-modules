from __future__ import annotations

from odoo import models
from odoo.http import request


class IrQweb(models.AbstractModel):
    """Keep the rendered-template cache from crossing consent states."""

    _inherit = 'ir.qweb'

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    def _get_template_cache_keys(self) -> list:
        """Add the granular consent state to the template cache key.

        Two visitors share core's binary ``cookies_allowed`` flag while having
        granted different purposes, and their markup differs.
        """
        return super()._get_template_cache_keys() + ['cookie_consent_state']

    def _prepare_frontend_environment(self, values: dict) -> models.Model:
        """Put the visitor's consent state into the rendering context."""
        irqweb = super()._prepare_frontend_environment(values)
        website = request.env['website'].get_current_website()
        if website and website._is_cookie_consent_active():
            categories = ','.join(sorted(website._get_granted_cookie_codes()))
            services = ','.join(sorted(website._get_granted_cookie_services()))
            irqweb = irqweb.with_context(
                cookie_consent_state=f'{categories}|{services}'
            )
        return irqweb
