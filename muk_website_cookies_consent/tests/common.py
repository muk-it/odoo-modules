from __future__ import annotations

import time

from odoo import models
from odoo.api import Environment
from odoo.tests import common

from odoo.addons.muk_website_cookies_consent.models import consent as consent_model
from odoo.addons.muk_website_cookies_consent.models import ir_http
from odoo.addons.muk_website_cookies_consent.models import website as website_model
from odoo.addons.muk_website_cookies_consent.tools.consent import (
    build_state,
    serialise_state,
)
from odoo.addons.muk_website_cookies_consent.tools.constants import CONSENT_COOKIE


class FakeGeoIP:
    """Stand in for the GeoIP lookup a real request carries."""

    country_code = 'AT'


class FakeHttpRequest:
    """Stand in for the werkzeug request the models read headers off."""

    def __init__(self, headers: dict | None = None) -> None:
        """Keep the headers the gating is meant to see."""
        self.headers = dict(headers or {})
        self.remote_addr = '81.223.45.67'


class FakeRequest:
    """Stand in for ``odoo.http.request`` while a test drives the models."""

    def __init__(
        self,
        env: Environment,
        cookie_value: str | None = None,
        headers: dict | None = None,
    ) -> None:
        """Expose the cookie, the headers and the environment of a visitor."""
        self.cookies = {CONSENT_COOKIE: cookie_value} if cookie_value else {}
        self.httprequest = FakeHttpRequest(headers)
        self.geoip = FakeGeoIP()
        self.env = env
        self.db = env.cr.dbname


class CookieConsentCommon(common.TransactionCase):
    """Shared fixtures for the cookie consent tests."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        """Set up a website with the consent bar on and the seeded registry."""
        super().setUpClass()
        cls.website = cls.env['website'].search([], limit=1)
        cls.website.write(
            {
                'cookies_bar': True,
                'block_third_party_domains': True,
                'cookie_blocking': True,
                'cookie_policy_version': 1,
            }
        )
        cls.category_essential = cls.env.ref(
            'muk_website_cookies_consent.category_essential'
        )
        cls.category_analytics = cls.env.ref(
            'muk_website_cookies_consent.category_analytics'
        )
        cls.category_marketing = cls.env.ref(
            'muk_website_cookies_consent.category_marketing'
        )
        cls.service_youtube = cls.env.ref('muk_website_cookies_consent.service_youtube')
        cls.service_linkedin = cls.env.ref(
            'muk_website_cookies_consent.service_linkedin'
        )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def as_visitor(self) -> models.Model:
        """Return the website as an anonymous visitor sees it.

        Stripping is intentionally skipped for website editors, so anything
        asserting what a real visitor receives has to drop those rights first.
        """
        return self.website.with_user(self.env.ref('base.public_user'))

    def build_cookie(
        self,
        codes: list[str],
        services: list[str] | None = None,
        policy_version: int | None = None,
        registry_hash: str | None = None,
        age_days: int = 0,
    ) -> str:
        """Return the consent cookie a browser would send for a decision.

        :param age_days: how long ago the decision was taken
        """
        now = int(time.time()) - age_days * 86400
        state = build_state(
            categories=codes,
            services=services or [],
            policy_version=(
                policy_version
                if policy_version is not None
                else self.website.cookie_policy_version
            ),
            registry_hash=(
                registry_hash
                if registry_hash is not None
                else self.website._get_cookie_registry_hash()
            ),
            lang_code='en_US',
            consent_uid='test-consent-uid',
            timestamp=now,
        )
        return serialise_state(state)

    def patch_request(
        self, cookie_value: str | None = None, headers: dict | None = None
    ) -> FakeRequest:
        """Install a fake request exposing cookies and headers to the models.

        The gating reads the visitor's cookie and the Sec-GPC header straight
        off the request, so the tests need a request to read from.
        """
        fake = FakeRequest(self.website.env, cookie_value, headers)
        for module in (consent_model, ir_http, website_model):
            self.patch(module, 'request', fake)
        return fake
