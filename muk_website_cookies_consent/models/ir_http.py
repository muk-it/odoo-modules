from __future__ import annotations

from odoo import models
from odoo.http import request

from odoo.addons.muk_website_cookies_consent.tools.constants import (
    CORE_OPTIONAL_CATEGORY,
)


class IrHttp(models.AbstractModel):
    """Answer core's cookie gate from the granular consent state."""

    _inherit = 'ir.http'

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @classmethod
    def _is_allowed_cookie(cls, cookie_type: str) -> bool:
        """Gate a cookie on the purpose it belongs to.

        Core only knows ``required`` and ``optional``, so an untaught caller
        gets its optional cookies gated on marketing. That branch must not
        defer to ``super()``, which reads core's own all-or-nothing cookie.
        """
        if cookie_type == 'optional':
            website = request.env['website'].get_current_website()
            if website and website._is_cookie_consent_active():
                return website._is_cookie_category_granted(CORE_OPTIONAL_CATEGORY)
        return super()._is_allowed_cookie(cookie_type)

    @classmethod
    def _is_allowed_cookie_category(cls, code: str) -> bool:
        """Return whether a named purpose is granted for this request.

        The entry point for other modules: a cookie belonging to analytics
        should ask for analytics rather than borrow core's blanket type.
        """
        website = request.env['website'].get_current_website()
        if not website or not website._is_cookie_consent_active():
            return True
        return website._is_cookie_category_granted(code)
