from __future__ import annotations

import re

from odoo import fields, models


class Cookie(models.Model):
    """One declared cookie or storage entry, listed in the cookie policy."""

    _name = 'muk_website_cookies_consent.cookie'
    _inherit = ['muk_website_cookies_consent.registry.mixin']
    _description = 'Cookie Declaration'
    _order = 'category_id, name'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    name = fields.Char(
        string='Name',
        required=True,
    )

    pattern = fields.Char(
        string='Name Pattern',
        help=(
            'Regular expression matching a family of cookies, e.g. "^_ga" for '
            'every Google Analytics cookie. Cookies matching it are deleted when '
            'this purpose is refused, instead of only the exact name above.'
        ),
    )

    service_id = fields.Many2one(
        comodel_name='muk_website_cookies_consent.service',
        string='Service',
        ondelete='set null',
    )

    category_id = fields.Many2one(
        comodel_name='muk_website_cookies_consent.category',
        string='Purpose',
        required=True,
        ondelete='cascade',
    )

    provider = fields.Char(
        string='Provider',
        translate=True,
    )

    description = fields.Text(
        string='Description',
        help='What this cookie is for, shown verbatim in the cookie policy.',
        translate=True,
    )

    duration = fields.Char(
        string='Retention',
        help='How long it persists, e.g. "1 year" or "Session".',
        translate=True,
    )

    storage_type = fields.Selection(
        selection=[
            ('http', 'HTTP Cookie'),
            ('local', 'Local Storage'),
            ('session', 'Session Storage'),
            ('indexeddb', 'IndexedDB'),
            ('pixel', 'Tracking Pixel'),
        ],
        string='Type',
        required=True,
        default='http',
    )

    necessity_justification = fields.Text(
        string='Necessity Justification',
        help=(
            'Why this is strictly necessary. The controller carries the burden '
            'of proving each such classification, so state the reason here.'
        ),
        translate=True,
    )

    website_id = fields.Many2one(
        comodel_name='website',
        related='category_id.website_id',
        string='Website',
        store=True,
    )

    active = fields.Boolean(
        string='Active',
        default=True,
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _matches_name(self, name: str) -> bool:
        """Return whether a stored key is covered by this declaration.

        Anchored, so a loose pattern cannot reach past its own purpose.
        """
        if not name:
            return False
        if name == self.name:
            return True
        if not self.pattern:
            return False
        try:
            return bool(re.match(f'(?:{self.pattern})', name))
        except re.error:
            return False
