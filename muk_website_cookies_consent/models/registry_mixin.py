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
    # Functions
    # ----------------------------------------------------------

    def _invalidate_cookie_registry(self) -> None:
        """Drop the memoised lookups and restate what the findings are."""
        self.env['website']._clear_cookie_registry_cache()
        self.env['muk_website_cookies_consent.observation']._resync_states()

    # ----------------------------------------------------------
    # ORM
    # ----------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list: list[dict]) -> models.Model:
        """Create the records and invalidate the registry fingerprint."""
        records = super().create(vals_list)
        self._invalidate_cookie_registry()
        return records

    def write(self, vals: dict) -> bool:
        """Write the records and invalidate the registry fingerprint."""
        result = super().write(vals)
        self._invalidate_cookie_registry()
        return result

    def unlink(self) -> bool:
        """Delete the records and invalidate the registry fingerprint."""
        result = super().unlink()
        self._invalidate_cookie_registry()
        return result
