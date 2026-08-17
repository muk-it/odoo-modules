from __future__ import annotations

from odoo import api, models


class CookieRegistryMixin(models.AbstractModel):
    """Drop the memoised registry lookups whenever the registry changes.

    The lookups are read once per rendered element and baked into cached
    pages, so every model the banner reads has to invalidate them on write.
    """

    _name = 'muk_website_cookies_consent.registry.mixin'
    _description = 'Cookie Registry Mixin'

    # ----------------------------------------------------------
    # ORM
    # ----------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list: list[dict]) -> models.Model:
        """Create the records and invalidate the registry fingerprint."""
        records = super().create(vals_list)
        self.env['website']._clear_cookie_registry_cache()
        return records

    def write(self, vals: dict) -> bool:
        """Write the records and invalidate the registry fingerprint."""
        result = super().write(vals)
        self.env['website']._clear_cookie_registry_cache()
        return result

    def unlink(self) -> bool:
        """Delete the records and invalidate the registry fingerprint."""
        result = super().unlink()
        self.env['website']._clear_cookie_registry_cache()
        return result
