from __future__ import annotations

from odoo import models


class CountryGroup(models.Model):
    """Keep the region lookup honest when a group's membership changes.

    The rule matching a country is memoised, and a rule can select countries
    through a group, so editing the group changes the answer without touching
    a rule. Inheriting the registry mixin drops the memo on that write too.
    """

    _name = 'res.country.group'
    _inherit = ['res.country.group', 'muk_website_cookies_consent.registry.mixin']
