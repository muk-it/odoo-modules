from __future__ import annotations

import json

from odoo import http, models
from odoo.http import request

from odoo.addons.muk_website_cookies_consent.tools.consent import parse_state
from odoo.addons.muk_website_cookies_consent.tools.constants import (
    CONSENT_COOKIE,
    ESSENTIAL_CODE,
    REGISTRY_HASH_LENGTH,
)


class CookieConsentController(http.Controller):
    """Public endpoints for recording consent and declaring GPC support."""

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _resolve_categories(
        self, website: models.Model, codes: list, answered: bool = True
    ) -> tuple[models.Model, models.Model]:
        """Return the granted and the refused purposes for a list of codes.

        Only what the dialog actually offered can be refused: a purpose the
        visitor was never shown was not declined by them. And a payload that
        answered nothing — an embed allowed in place — refuses nothing at all,
        or the record would file decisions the visitor never took.

        :param answered: whether the payload came from answering the banner
        """
        wanted = {str(code) for code in codes or []}
        categories = website._get_offered_cookie_categories()
        granted = categories.filtered(
            lambda c: c.code in wanted or c.code == ESSENTIAL_CODE
        )
        denied = (categories - granted) if answered else categories.browse()
        return granted, denied

    # ----------------------------------------------------------
    # Routes
    # ----------------------------------------------------------

    @http.route(
        '/muk_website_cookies_consent/consent',
        type='json',
        auth='public',
        website=True,
        methods=['POST'],
    )
    def record_consent(
        self, state: dict | None = None, action: str = '', source: str = '', **kwargs
    ) -> dict:
        """Record one consent decision as proof.

        The choice is already in the visitor's cookie by the time this runs, so
        this endpoint decides nothing and only writes the evidence. Everything
        filed is taken from the stored cookie rather than the posted copy: a log
        that anyone can write is not proof of anything.

        :param state: the payload the browser stored in the consent cookie
        :return: the reference the decision was filed under, empty when off
        """
        website = request.env['website'].get_current_website()
        if not isinstance(state, dict) or not website._is_cookie_consent_active():
            return {}
        consent_uid = str(state.get('uid') or '')[:64]
        if not consent_uid:
            return {}
        stored = parse_state(request.httprequest.cookies.get(CONSENT_COOKIE))
        if not stored or stored.get('uid') != consent_uid:
            return {}
        if sorted(map(str, stored.get('cats') or [])) != sorted(
            map(str, state.get('cats') or [])
        ):
            return {}
        answered = bool(stored.get('ans', 1))
        granted, denied = self._resolve_categories(
            website, stored.get('cats'), answered
        )
        services = website._get_cookie_services().filtered(
            lambda s: s.technical_name in {str(n) for n in stored.get('svcs') or []}
        )
        rule = website._get_cookie_geo_rule()
        valid_actions = dict(
            request.env['muk_website_cookies_consent.consent']
            ._fields['action']
            .selection
        )
        valid_sources = dict(
            request.env['muk_website_cookies_consent.consent']
            ._fields['source']
            .selection
        )
        record = request.env['muk_website_cookies_consent.consent']._log_decision(
            website,
            {
                'consent_uid': consent_uid,
                'action': action if action in valid_actions else 'custom',
                'source': source if source in valid_sources else 'banner',
                'granted_category_ids': [(6, 0, granted.ids)],
                'denied_category_ids': [(6, 0, denied.ids)],
                'granted_service_ids': [(6, 0, services.ids)],
                'policy_version': int(stored.get('pv') or 0),
                'registry_hash': str(stored.get('rh') or '')[:REGISTRY_HASH_LENGTH],
                'banner_version': website._get_cookie_banner_version(),
                'lang_code': str(stored.get('lang') or '')[:16],
                'geo_rule_id': rule.id or False,
                'jurisdiction': request.geoip.get('country_code') or '',
                'lifetime_days': website._get_cookie_lifetime_days(),
                'consent_mode_pushed': website.cookie_consent_mode != 'off',
                'user_agent': request.httprequest.user_agent.string[:512],
                'visitor_id': request.env['website.visitor']
                ._get_visitor_from_request()
                .id
                or False,
            },
        )
        return {'reference': record.consent_uid} if record else {}

    @http.route(
        '/.well-known/gpc.json',
        type='http',
        auth='public',
        website=True,
        sitemap=False,
    )
    def gpc_json(self, **kwargs) -> http.Response:
        """Declare that this site honours Global Privacy Control.

        Only served once the setting has been turned on: publishing the
        declaration while not acting on the signal is precisely the
        misrepresentation regulators have penalised.
        """
        website = request.env['website'].get_current_website()
        if not website.cookie_publish_gpc_json or not website.cookie_respect_gpc:
            return request.not_found()
        payload = {
            'gpc': True,
            'lastUpdate': str(website.write_date.date()),
        }
        return request.make_response(
            json.dumps(payload),
            headers=[('Content-Type', 'application/json')],
        )
