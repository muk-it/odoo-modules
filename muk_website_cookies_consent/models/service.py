from __future__ import annotations

import re
from urllib.parse import urlsplit

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class CookieService(models.Model):
    """A third-party service gated behind the consent of its purpose."""

    _name = 'muk_website_cookies_consent.service'
    _inherit = ['muk_website_cookies_consent.registry.mixin']
    _description = 'Cookie Service'
    _explanation = (
        'A third-party service gated by cookie consent, such as a video '
        'platform or an analytics tool, with the hosts it loads from and the '
        'purpose that releases it. Use it to see which scripts and embeds are '
        'blocked until consent.'
    )
    _order = 'sequence, name'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    name = fields.Char(
        string='Name',
        required=True,
        translate=True,
    )

    technical_name = fields.Char(
        string='Technical Name',
        help='Identifier used in the consent cookie and in data-muk-cookie-service.',
        required=True,
    )

    category_id = fields.Many2one(
        comodel_name='muk_website_cookies_consent.category',
        string='Purpose',
        required=True,
        ondelete='cascade',
    )

    provider = fields.Char(
        string='Provider',
        help='The company that receives the data, named in the cookie policy.',
        translate=True,
    )

    domains = fields.Text(
        string='Domains',
        help=(
            'One host per line. Scripts and embeds loaded from these hosts, or '
            'any of their subdomains, are blocked until this purpose is granted.'
        ),
    )

    contextual_only = fields.Boolean(
        string='Ask In Place Only',
        help=(
            'Keep this service out of the preference centre and ask for it '
            'where it is embedded instead, via a placeholder on the blocked '
            'element. Suited to video embeds and maps.'
        ),
    )

    placeholder_text = fields.Text(
        string='Placeholder Text',
        help='Shown on the blocked element in place of the embed.',
        translate=True,
    )

    sequence = fields.Integer(
        string='Sequence',
        default=10,
    )

    website_id = fields.Many2one(
        comodel_name='website',
        related='category_id.website_id',
        string='Website',
        store=True,
    )

    cookie_ids = fields.One2many(
        comodel_name='muk_website_cookies_consent.cookie',
        inverse_name='service_id',
        string='Cookies',
    )

    active = fields.Boolean(
        string='Active',
        default=True,
    )

    _technical_name_uniq = models.Constraint(
        'unique (technical_name, website_id)',
        'A service with this technical name already exists for this website.',
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _normalise_host(self, host: str) -> str:
        """Return a host lowercased and stripped of a leading ``www.``.

        Mirrors what core's cookie watcher does client-side, so a domain
        entered either way matches the same requests.
        """
        host = (host or '').strip().lower()
        return host.removeprefix('www.')

    def _get_domain_list(self) -> list[str]:
        """Return the configured patterns, normalised and de-duplicated."""
        patterns = {
            self._normalise_host(line)
            for line in (self.domains or '').splitlines()
            if line.strip()
        }
        return sorted(patterns)

    @api.model
    def _split_pattern(self, pattern: str) -> tuple[str, str]:
        """Return a pattern split into its host and its path prefix.

        A path narrows a shared host to one product: ``google.com/maps`` gates
        an embedded map without gating every other request to ``google.com``.
        :return: the host, and the path prefix or an empty string
        """
        host, _, path = pattern.partition('/')
        return host, f'/{path}' if path else ''

    def _matches_url(self, url: str) -> bool:
        """Return whether a URL is served by one of this service's patterns.

        A host also covers its subdomains: ``youtube.com`` matches
        ``player.youtube.com`` but not ``youtube-nocookie.com``.
        :param url: the value of a src attribute, absolute or protocol-relative
        """
        parts = urlsplit(url or '')
        host = self._normalise_host(parts.hostname or '')
        if not host:
            return False
        for pattern in self._get_domain_list():
            domain, prefix = self._split_pattern(pattern)
            if host != domain and not host.endswith(f'.{domain}'):
                continue
            if not prefix or (parts.path or '').startswith(prefix):
                return True
        return False

    # ----------------------------------------------------------
    # Constraints
    # ----------------------------------------------------------

    @api.constrains('technical_name')
    def _check_technical_name(self) -> None:
        """Keep technical names to plain identifiers.

        The granted names are joined into the cache keys, so a separator inside
        one would make two different consent states share a key.
        :raise ValidationError: when a name is not a plain identifier
        """
        for service in self:
            if not re.fullmatch(r'[a-z0-9_]+', service.technical_name or ''):
                raise ValidationError(
                    self.env._(
                        'The technical name "%(name)s" may only contain lowercase '
                        'letters, digits and underscores.',
                        name=service.technical_name,
                    )
                )
