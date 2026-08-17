from __future__ import annotations

import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.muk_website_cookies_consent.tools.constants import (
    CONSENT_MODE_SIGNALS,
    ESSENTIAL_CODE,
)


class CookieCategory(models.Model):
    """A consent purpose the visitor decides on, such as analytics."""

    _name = 'muk_website_cookies_consent.category'
    _inherit = ['muk_website_cookies_consent.registry.mixin']
    _description = 'Cookie Category'
    _order = 'sequence, id'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    name = fields.Char(
        string='Name',
        required=True,
        translate=True,
    )

    code = fields.Char(
        string='Code',
        help='Technical identifier used in the consent cookie and in markup.',
        required=True,
    )

    description = fields.Text(
        string='Description',
        help='Shown to the visitor in the preference centre.',
        translate=True,
    )

    sequence = fields.Integer(
        string='Sequence',
        default=10,
    )

    essential = fields.Boolean(
        string='Strictly Necessary',
        help=(
            'Strictly necessary purposes need no consent, so their toggle is '
            'locked on. Everything else must be granted by the visitor.'
        ),
    )

    default_enabled = fields.Boolean(
        string='Pre-selected',
        help=(
            'Pre-selecting a purpose that is not strictly necessary produces '
            'invalid consent under the GDPR and is refused on save.'
        ),
    )

    consent_mode_signals = fields.Char(
        string='Consent Mode Signals',
        help=(
            'Space-separated Google Consent Mode v2 signals granted with this '
            'purpose, e.g. "analytics_storage".'
        ),
    )

    website_id = fields.Many2one(
        comodel_name='website',
        string='Website',
        help='Leave empty to apply to every website.',
        ondelete='cascade',
    )

    service_ids = fields.One2many(
        comodel_name='muk_website_cookies_consent.service',
        inverse_name='category_id',
        string='Services',
    )

    cookie_ids = fields.One2many(
        comodel_name='muk_website_cookies_consent.cookie',
        inverse_name='category_id',
        string='Cookies',
    )

    active = fields.Boolean(
        string='Active',
        default=True,
    )

    _sql_constraints = [
        (
            'code_uniq',
            'unique (code, website_id)',
            'A purpose with this code already exists for this website.',
        ),
    ]

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _get_consent_mode_signals(self) -> list[str]:
        """Return the Consent Mode signals this purpose grants."""
        return (self.consent_mode_signals or '').split()

    # ----------------------------------------------------------
    # Constraints
    # ----------------------------------------------------------

    @api.constrains('essential', 'default_enabled')
    def _check_default_enabled(self) -> None:
        """Forbid pre-selecting a purpose that is not strictly necessary."""
        for category in self:
            if category.default_enabled and not category.essential:
                raise ValidationError(
                    _(
                        'The purpose "%(name)s" cannot be pre-selected: consent '
                        'given through a pre-ticked box is not valid consent. '
                        'Only strictly necessary purposes may default to on.',
                        name=category.name,
                    )
                )

    @api.constrains('consent_mode_signals')
    def _check_consent_mode_signals(self) -> None:
        """Reject Consent Mode signals Google does not define."""
        for category in self:
            unknown = set(category._get_consent_mode_signals()) - set(
                CONSENT_MODE_SIGNALS
            )
            if unknown:
                raise ValidationError(
                    _(
                        'Unknown Google Consent Mode signals: %(unknown)s.\n'
                        'Valid signals are: %(valid)s.',
                        unknown=', '.join(sorted(unknown)),
                        valid=', '.join(CONSENT_MODE_SIGNALS),
                    )
                )

    @api.constrains('code')
    def _check_code_format(self) -> None:
        """Keep codes to plain identifiers.

        Granted codes are joined into the page and template cache keys, so a
        separator inside one would make two consent states share a key.
        """
        for category in self:
            if not re.fullmatch(r'[a-z0-9_]+', category.code or ''):
                raise ValidationError(
                    _(
                        'The code "%(code)s" may only contain lowercase letters, '
                        'digits and underscores.',
                        code=category.code,
                    )
                )

    @api.constrains('essential', 'code')
    def _check_essential_code(self) -> None:
        """Keep the reserved essential code bound to a strictly necessary purpose."""
        for category in self:
            if (category.code == ESSENTIAL_CODE) != bool(category.essential):
                raise ValidationError(
                    _(
                        'The code "%(code)s" is reserved for the strictly '
                        'necessary purpose and cannot be used for another one.',
                        code=ESSENTIAL_CODE,
                    )
                )
