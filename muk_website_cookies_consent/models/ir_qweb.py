from __future__ import annotations

from odoo import models


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
