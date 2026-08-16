from __future__ import annotations

from odoo import api, fields, models, tools

from odoo.addons.muk_website_cookies_consent.tools.constants import (
    DEFAULT_LIFETIME_DAYS,
)


class CookieGeoRule(models.Model):
    """How long a decision is relied on in one region, and on whose authority."""

    _name = 'muk_website_cookies_consent.geo.rule'
    _inherit = ['muk_website_cookies_consent.registry.mixin']
    _description = 'Cookie Consent Region Rule'
    _order = 'sequence, id'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    name = fields.Char(
        string='Name',
        required=True,
        translate=True,
    )

    country_ids = fields.Many2many(
        comodel_name='res.country',
        relation='muk_cookies_geo_rule_country_rel',
        column1='rule_id',
        column2='country_id',
        string='Countries',
        help='Leave empty together with country groups to match every visitor.',
    )

    country_group_ids = fields.Many2many(
        comodel_name='res.country.group',
        relation='muk_cookies_geo_rule_country_group_rel',
        column1='rule_id',
        column2='country_group_id',
        string='Country Groups',
    )

    lifetime_days = fields.Integer(
        string='Consent Lifetime (days)',
        help='How long a decision is relied on before the visitor is asked again.',
        required=True,
        default=DEFAULT_LIFETIME_DAYS,
    )

    source_note = fields.Text(
        string='Source',
        help=(
            'Where the retention figure comes from. Shown next to the setting so '
            'nobody mistakes a practitioner convention for a statutory rule.'
        ),
        translate=True,
    )

    sequence = fields.Integer(
        string='Sequence',
        help='The first matching rule wins, so put specific regions above catch-alls.',
        default=10,
    )

    website_id = fields.Many2one(
        comodel_name='website',
        string='Website',
        help='Leave empty to apply to every website.',
        ondelete='cascade',
    )

    active = fields.Boolean(
        string='Active',
        default=True,
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _matches_country(self, country_code: str | None) -> bool:
        """Return whether this rule covers the given ISO 3166-1 alpha-2 code.

        A rule with neither countries nor groups is a catch-all and matches
        everything, including a visitor whose country could not be resolved.
        """
        if not self.country_ids and not self.country_group_ids:
            return True
        if not country_code:
            return False
        code = country_code.upper()
        if code in self.country_ids.mapped('code'):
            return True
        return code in self.country_group_ids.country_ids.mapped('code')

    @api.model
    @tools.ormcache('country_code', 'website.id')
    def _find_id_for_country(
        self, country_code: str | None, website: models.Model
    ) -> int | None:
        """Return the id of the first rule matching a country on a website.

        Memoised because the rule decides the consent lifetime, which the
        gating asks for once per element of a rendered page. Sorted in Python
        rather than by the ORM, which would leave the placement of the global
        rules (NULL ``website_id``) up to the database.
        """
        rules = self.sudo().search([('website_id', 'in', [website.id, False])])
        for rule in rules.sorted(
            lambda r: (not r.website_id, r.sequence, r.id)  # noqa: PLW0108
        ):
            if rule._matches_country(country_code):
                return rule.id
        return None

    @api.model
    def _find_for_country(
        self, country_code: str | None, website: models.Model
    ) -> models.Model:
        """Return the first rule matching a country on the given website.

        Website-specific rules are considered before global ones so a single
        website can diverge without duplicating the whole set. Sudo, like the
        search it replaces: the public user cannot read a rule.
        """
        rule_id = self._find_id_for_country(country_code, website)
        return self.sudo().browse(rule_id) if rule_id else self.sudo().browse()
