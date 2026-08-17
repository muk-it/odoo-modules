from __future__ import annotations

from odoo import models
from odoo.http import request

from odoo.addons.website.models import ir_http


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

    def _post_processing_att(self, tagName: str, atts: dict) -> dict:  # noqa: N803
        """Decide per service which elements are stripped from the markup.

        Nothing on this branch strips a third-party tag server-side, so this is
        where the module puts the decision Odoo 19 makes in core: the registry
        answers it per service, while the template is compiled, which is early
        enough that a blocked tag never reaches the browser at all.
        """
        atts = super()._post_processing_att(tagName, atts)
        if atts.get('data-no-post-process'):
            return atts
        if (
            self.env.context.get('inherit_branding')
            or self.env.context.get('rendering_bundle')
            or self.env.context.get('edit_translations')
            or self.env.context.get('debug')
            or (request and request.session.debug)
        ):
            return atts
        website = ir_http.get_request_website()
        if not website and self.env.context.get('website_id'):
            website = self.env['website'].browse(self.env.context['website_id'])
        if website and website._should_remove_third_party_trackers():
            website._remove_third_party_trackers(tagName, atts, ['domains', 'classes'])
        return atts

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
