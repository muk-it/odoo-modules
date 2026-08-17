from __future__ import annotations

import hashlib
import ipaddress
import logging
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.http import request

from odoo.addons.muk_website_cookies_consent.tools.constants import (
    CONSENT_ACTIONS,
    CONSENT_SOURCES,
    DEFAULT_LOG_RETENTION_DAYS,
)

_logger = logging.getLogger(__name__)


class CookieConsent(models.Model):
    """An immutable record of one consent decision, kept as proof.

    GDPR Art. 7(1) puts the burden of demonstrating consent on the
    controller, so a record captures not only what was decided but what the
    visitor was shown when they decided it: the policy version, the hash of
    the cookie registry in force, and the banner version.
    """

    _name = 'muk_website_cookies_consent.consent'
    _description = 'Cookie Consent Record'
    _rec_name = 'consent_uid'
    _order = 'create_date desc, id desc'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    consent_uid = fields.Char(
        string='Consent Reference',
        help=(
            'Random reference shared by every decision of one browser. Not '
            'derived from anything identifying the visitor.'
        ),
        required=True,
        index=True,
    )

    website_id = fields.Many2one(
        comodel_name='website',
        string='Website',
        required=True,
        ondelete='cascade',
    )

    visitor_id = fields.Many2one(
        comodel_name='website.visitor',
        string='Visitor',
        ondelete='set null',
    )

    action = fields.Selection(
        selection=list(CONSENT_ACTIONS),
        string='Decision',
        required=True,
    )

    source = fields.Selection(
        selection=list(CONSENT_SOURCES),
        string='Given Through',
        required=True,
        default='banner',
    )

    granted_category_ids = fields.Many2many(
        comodel_name='muk_website_cookies_consent.category',
        relation='muk_cookies_consent_granted_rel',
        column1='consent_id',
        column2='category_id',
        string='Granted Purposes',
    )

    denied_category_ids = fields.Many2many(
        comodel_name='muk_website_cookies_consent.category',
        relation='muk_cookies_consent_denied_rel',
        column1='consent_id',
        column2='category_id',
        string='Refused Purposes',
        help='Recorded explicitly: a refusal is as much evidence as a grant.',
    )

    granted_service_ids = fields.Many2many(
        comodel_name='muk_website_cookies_consent.service',
        relation='muk_cookies_consent_service_rel',
        column1='consent_id',
        column2='service_id',
        string='Granted Services',
    )

    policy_version = fields.Integer(
        string='Policy Version',
        required=True,
    )

    registry_hash = fields.Char(
        string='Registry Hash',
        help=(
            'Fingerprint of the purposes, services and cookies declared when '
            'consent was given, so the disclosure shown can be reconstructed.'
        ),
        required=True,
    )

    banner_version = fields.Char(
        string='Banner Version',
        help='Module version that rendered the banner.',
    )

    lang_code = fields.Char(
        string='Language',
        help='The language the banner was shown in.',
    )

    geo_rule_id = fields.Many2one(
        comodel_name='muk_website_cookies_consent.geo.rule',
        string='Region Rule',
        ondelete='set null',
    )

    jurisdiction = fields.Char(
        string='Country',
        help='Country resolved from the request when consent was given.',
    )

    lifetime_days = fields.Integer(
        string='Lifetime (days)',
    )

    consent_mode_pushed = fields.Boolean(
        string='Consent Mode Signalled',
        help='Whether the decision was pushed to Google Consent Mode.',
    )

    user_agent = fields.Char(
        string='User Agent',
    )

    ip_hash = fields.Char(
        string='IP Fingerprint',
        help=(
            'Salted SHA-256 of the truncated visitor IP. Enough to match a '
            'record to a claimant who knows their address and roughly when they '
            'consented, while storing no readable address.'
        ),
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _truncate_ip(self, address: str | None) -> str:
        """Return the address with its host part dropped.

        IPv4 keeps its /24 network, IPv6 its /64, so the value identifies a
        network rather than a device before it is ever hashed.
        """
        if not address:
            return ''
        try:
            parsed = ipaddress.ip_address(address)
        except ValueError:
            return ''
        prefix = 24 if parsed.version == 4 else 64
        return str(ipaddress.ip_network(f'{parsed}/{prefix}', strict=False))

    @api.model
    def _hash_ip(self, address: str | None) -> str:
        """Return a salted digest of the truncated address.

        Salted with the database secret, so the digests survive neither a
        rainbow table of every address on the internet nor correlation across
        databases.
        """
        network = self._truncate_ip(address)
        if not network:
            return ''
        salt = self.env['ir.config_parameter'].sudo().get_param('database.secret') or ''
        return hashlib.sha256(f'{salt}:{network}'.encode()).hexdigest()

    @api.model
    def _log_decision(self, website: models.Model, values: dict) -> models.Model:
        """Record one decision, never overwriting an earlier one.

        Logging must not be able to break consent: the visitor's cookie is
        already written by the time this runs, so a failure here is reported
        and swallowed rather than propagated.

        :return: the created record, or empty when disabled or on failure
        """
        if not website.cookie_log_consent:
            return self.browse()
        payload = dict(values, website_id=website.id)
        if website.cookie_log_ip and request:
            payload['ip_hash'] = self._hash_ip(request.httprequest.remote_addr)
        try:
            return self.sudo().create(payload)
        except Exception:
            _logger.exception('Could not record a cookie consent decision.')
            return self.browse()

    # ----------------------------------------------------------
    # ORM
    # ----------------------------------------------------------

    def write(self, vals: dict) -> bool:
        """Refuse every change: a record that can be edited proves nothing.

        :raise UserError: always
        """
        raise UserError(
            _(
                'Consent records cannot be changed. They are the evidence that '
                'a decision was taken, so a later decision is filed as its own '
                'record instead.'
            )
        )

    def unlink(self) -> bool:
        """Refuse deletion except by the retention cron.

        :raise UserError: when something other than the purge deletes records
        """
        if not self.env.context.get('cookie_consent_purge'):
            raise UserError(
                _(
                    'Consent records cannot be deleted here. They go when they '
                    'pass the retention period, or with the website they belong '
                    'to.'
                )
            )
        return super().unlink()

    # ----------------------------------------------------------
    # Cron
    # ----------------------------------------------------------

    @api.model
    def _cron_purge_records(self) -> None:
        """Delete consent records past their retention period."""
        limit = fields.Datetime.now() - timedelta(days=DEFAULT_LOG_RETENTION_DAYS)
        expired = self.search([('create_date', '<', limit)])
        if expired:
            _logger.info('Purging %s expired cookie consent records.', len(expired))
            expired.with_context(cookie_consent_purge=True).unlink()
