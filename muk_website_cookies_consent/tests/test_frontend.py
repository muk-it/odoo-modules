from __future__ import annotations

import json
import re
import time
from urllib.parse import quote

from odoo.tests import HttpCase, tagged

RENDER_TIMEOUT = 120


@tagged('post_install', '-at_install')
class TestFrontend(HttpCase):
    """What an actual visitor receives from the server."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.website = cls.env['website'].search([], limit=1)
        cls.website.write({'cookies_bar': True, 'block_third_party_domains': True})

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def open_page(self, path: str = '/') -> str:
        """Return a rendered page, allowing for a cold render.

        Every distinct consent state and configuration is a deliberate cache
        miss, so these are full renders rather than cached copies.

        :param path: the URL path to fetch
        :return: the response body
        """
        return self.url_open(path, timeout=RENDER_TIMEOUT).text

    def send_decision(self, codes: list[str]) -> str:
        """Send a stored decision back as a browser would.

        :param codes: the purpose codes the decision grants
        :return: the rendered homepage
        """
        state = {
            'v': 1,
            'uid': 'cookie-roundtrip',
            'cats': codes,
            'svcs': [],
            'pv': self.website.cookie_policy_version,
            'rh': self.website._get_cookie_registry_hash(),
            'ts': int(time.time()),
            'rts': int(time.time()),
            'lang': 'en_US',
        }
        self.opener.cookies.pop('muk_cookie_consent', None)
        self.opener.cookies.set('muk_cookie_consent', quote(json.dumps(state)))
        return self.open_page()

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_banner_is_served_to_a_first_time_visitor(self):
        body = self.open_page('/')
        self.assertIn('website_cookies_bar', body)
        self.assertIn('data-muk-cookie-ask="1"', body)

    def test_both_choices_are_on_the_first_layer(self):
        body = self.open_page('/')
        self.assertIn('mk_cookies_accept_all', body)
        self.assertIn(
            'mk_cookies_reject_all',
            body,
            'Refuse all has to be reachable without opening a second layer.',
        )

    def test_the_dialog_is_announced_as_one(self):
        body = self.open_page('/')
        tag = re.search(r'<div[^>]*aria-labelledby="muk_cookies_title"[^>]*>', body)
        self.assertTrue(tag, 'The notice has to be a labelled dialog.')
        self.assertIn('role="dialog"', tag.group(0))
        self.assertIn('id="muk_cookies_title"', body)
        self.assertNotIn(
            'aria-modal',
            tag.group(0),
            'The notice leaves the page usable, so it must not claim modality; '
            'the preference centre claims it when it opens.',
        )

    def test_the_preference_centre_ships_with_the_page(self):
        body = self.open_page('/')
        self.assertIn("data-layer='preferences'", body.replace('"', "'"))
        self.assertIn("name='muk_cookie_category'", body.replace('"', "'"))

    def test_the_essential_toggle_is_locked_on(self):
        body = self.open_page('/')
        self.assertRegex(
            body.replace('"', "'").replace('\n', ' '),
            r"id='muk_cookie_cat_essential'[^>]*checked",
        )

    def test_optional_toggles_start_off(self):
        body = self.open_page('/').replace('"', "'").replace('\n', ' ')
        marker = body.split("id='muk_cookie_cat_analytics'")[1][:200]
        self.assertNotIn(
            'checked',
            marker,
            'A pre-ticked optional purpose would not be valid consent.',
        )

    def test_the_way_back_is_on_every_page(self):
        body = self.open_page('/')
        self.assertIn('mk_cookies_reopen', body)

    def test_a_first_visit_is_offered_no_way_out_but_a_decision(self):
        body = self.open_page('/')
        match = re.search(r'<button[^>]*id="muk_cookies_dismiss"[^>]*>', body)
        self.assertTrue(match, 'The banner lost the control that closes a reopening.')
        self.assertIn(
            'd-none',
            match.group(0),
            'A visitor who has decided nothing must have nothing to dismiss.',
        )

    def test_consent_mode_defaults_are_denied_before_a_decision(self):
        self.website.google_analytics_key = 'G-TESTKEY123'
        body = self.open_page('/')
        self.assertIn('tracking_code_config', body)
        self.assertIn('"analytics_storage": "denied"', body)
        self.assertIn('"wait_for_update": 500', body)

    def test_basic_mode_withholds_the_google_loader(self):
        self.website.write(
            {'google_analytics_key': 'G-TESTKEY123', 'cookie_consent_mode': 'basic'}
        )
        body = self.open_page('/')
        self.assertNotIn(
            'googletagmanager.com/gtag/js',
            body,
            'Basic mode must not load a Google tag before the visitor decides.',
        )

    def test_advanced_mode_loads_the_google_loader(self):
        self.website.write(
            {
                'google_analytics_key': 'G-TESTKEY123',
                'cookie_consent_mode': 'advanced',
            }
        )
        body = self.open_page('/')
        self.assertIn('googletagmanager.com/gtag/js', body)

    def test_a_container_id_is_deployed_by_odoo_not_by_this_module(self):
        self.website.write(
            {
                'google_analytics_key': 'GTM-TESTKEY',
                'cookie_consent_mode': 'advanced',
            }
        )
        body = self.open_page('/')
        self.assertNotIn(
            'googletagmanager.com/gtm.js',
            body,
            'Deploying a tag is not this module’s job; it only gates one.',
        )
        self.assertIn('googletagmanager.com/gtag/js?id=GTM-TESTKEY', body)

    def test_gpc_is_not_declared_until_it_is_turned_on(self):
        self.website.cookie_publish_gpc_json = False
        self.assertEqual(
            self.url_open('/.well-known/gpc.json', timeout=RENDER_TIMEOUT).status_code,
            404,
        )

    def test_gpc_declaration_is_served_once_enabled(self):
        self.website.write(
            {'cookie_respect_gpc': True, 'cookie_publish_gpc_json': True}
        )
        response = self.url_open('/.well-known/gpc.json', timeout=RENDER_TIMEOUT)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['gpc'])
        self.assertIn('lastUpdate', response.json())

    def test_the_policy_page_lists_the_declared_cookies(self):
        body = self.open_page('/cookie-policy')
        self.assertIn('session_id', body)
        self.assertIn('Strictly necessary', body)
        self.assertIn(
            'Change my cookie choices',
            body,
            'The policy page is where a visitor goes to change their mind.',
        )

    def test_the_banner_links_to_the_page_odoo_publishes(self):
        body = self.open_page('/')
        self.assertIn('href="/cookie-policy"', body)

    def test_the_banner_links_where_the_site_keeps_its_policy(self):
        self.website.cookie_policy_url = '/legal/cookies'
        try:
            body = self.open_page('/')
        finally:
            self.website.cookie_policy_url = False
        self.assertIn('href="/legal/cookies"', body)
        self.assertNotIn('href="/cookie-policy"', body)

    def test_the_policy_page_states_the_gpc_position(self):
        self.website.cookie_respect_gpc = True
        body = self.open_page('/cookie-policy')
        self.assertIn('Global Privacy Control', body)
        self.assertNotIn(
            'We do not currently support Do Not Track',
            body,
            'Core claims no signal support, which would be untrue here.',
        )

    def test_a_stored_decision_stops_the_banner_asking(self):
        state = {
            'v': 1,
            'uid': 'cookie-roundtrip',
            'cats': ['essential', 'analytics'],
            'svcs': [],
            'pv': self.website.cookie_policy_version,
            'rh': self.website._get_cookie_registry_hash(),
            'ts': int(time.time()),
            'rts': int(time.time()),
            'lang': 'en_US',
        }
        self.opener.cookies['muk_cookie_consent'] = quote(json.dumps(state))
        body = self.open_page('/')
        self.assertIn(
            'data-muk-cookie-ask="0"',
            body,
            'A decision the browser sends back must be recognised by the server.',
        )

    def test_a_refusal_keeps_everything_optional_blocked(self):
        self.website.write(
            {
                'google_analytics_key': 'G-TESTKEY123',
                'cookie_consent_mode': 'basic',
            }
        )
        body = self.send_decision(['essential'])
        self.assertIn('data-muk-cookie-ask="0"', body)
        self.assertNotIn(
            'googletagmanager.com/gtag/js',
            body,
            'A refusal must leave the Google tag unloaded.',
        )
        self.assertIn('"analytics_storage": "denied"', body)

    def test_withdrawing_after_consent_takes_effect(self):
        self.website.write(
            {
                'google_analytics_key': 'G-TESTKEY123',
                'cookie_consent_mode': 'advanced',
            }
        )
        granted = self.send_decision(['essential', 'analytics', 'marketing'])
        self.assertIn('"analytics_storage": "granted"', granted)
        withdrawn = self.send_decision(['essential'])
        self.assertIn(
            '"analytics_storage": "denied"',
            withdrawn,
            'Withdrawal has to take effect on the very next page.',
        )
        self.assertIn('"ad_storage": "denied"', withdrawn)

    def test_pages_are_not_cached_across_consent_states(self):
        self.website.write(
            {
                'google_analytics_key': 'G-TESTKEY123',
                'cookie_consent_mode': 'advanced',
            }
        )
        analytics_only = self.send_decision(['essential', 'analytics'])
        marketing_only = self.send_decision(['essential', 'marketing'])
        self.assertIn('"analytics_storage": "granted"', analytics_only)
        self.assertIn(
            '"analytics_storage": "denied"',
            marketing_only,
            'A page rendered for one consent state must never be served to '
            'a visitor who granted something else.',
        )
        self.assertIn('"ad_storage": "granted"', marketing_only)

    def test_a_decision_the_visitor_never_made_is_not_recorded(self):
        state = {
            'v': 1,
            'uid': 'forged-uid',
            'cats': ['essential', 'marketing'],
            'svcs': [],
            'pv': self.website.cookie_policy_version,
            'rh': self.website._get_cookie_registry_hash(),
            'ts': 1786000000,
            'rts': 1786000000,
            'lang': 'en_US',
        }
        self.opener.cookies.pop('muk_cookie_consent', None)
        before = self.env['muk_website_cookies_consent.consent'].search_count([])
        self.opener.post(
            f'{self.base_url()}/muk_website_cookies_consent/consent',
            json={
                'jsonrpc': '2.0',
                'method': 'call',
                'id': 1,
                'params': {'state': state, 'action': 'accept_all', 'source': 'banner'},
            },
        )
        self.assertEqual(
            self.env['muk_website_cookies_consent.consent'].search_count([]),
            before,
            'A payload with no matching consent cookie is not evidence.',
        )

    def test_a_first_visit_is_not_served_a_refusers_page(self):
        asked = self.open_page()
        self.assertIn('data-muk-cookie-ask="1"', asked)
        refused = self.send_decision(['essential'])
        self.assertIn('data-muk-cookie-ask="0"', refused)
        self.opener.cookies.pop('muk_cookie_consent', None)
        again = self.open_page()
        self.assertIn(
            'data-muk-cookie-ask="1"',
            again,
            'A refusal and a first visit grant the same purposes, so the cached '
            'page of one must never suppress the banner for the other.',
        )

    def test_gpc_declaration_needs_the_signal_to_be_honoured(self):
        self.website.write(
            {'cookie_respect_gpc': False, 'cookie_publish_gpc_json': True}
        )
        self.assertEqual(
            self.url_open('/.well-known/gpc.json', timeout=RENDER_TIMEOUT).status_code,
            404,
            'Declaring GPC support while ignoring the signal is the '
            'misrepresentation the rule exists to prevent.',
        )

    def test_recording_a_decision_over_http(self):
        state = {
            'v': 1,
            'uid': 'http-test-uid',
            'cats': ['essential', 'analytics'],
            'svcs': [],
            'pv': self.website.cookie_policy_version,
            'rh': self.website._get_cookie_registry_hash(),
            'ts': 1786000000,
            'rts': 1786000000,
            'lang': 'en_US',
        }
        self.opener.cookies.pop('muk_cookie_consent', None)
        self.opener.cookies.set('muk_cookie_consent', quote(json.dumps(state)))
        payload = {'state': state, 'action': 'custom', 'source': 'preferences'}
        result = self.opener.post(
            f'{self.base_url()}/muk_website_cookies_consent/consent',
            json={'jsonrpc': '2.0', 'method': 'call', 'id': 1, 'params': payload},
        ).json()
        self.assertEqual(result['result']['reference'], 'http-test-uid')
        record = self.env['muk_website_cookies_consent.consent'].search(
            [('consent_uid', '=', 'http-test-uid')]
        )
        self.assertEqual(len(record), 1)
        self.assertEqual(record.action, 'custom')
        self.assertIn(
            self.env.ref('muk_website_cookies_consent.category_analytics'),
            record.granted_category_ids,
        )
        self.assertIn(
            self.env.ref('muk_website_cookies_consent.category_marketing'),
            record.denied_category_ids,
        )

    def test_a_junk_payload_records_nothing(self):
        before = self.env['muk_website_cookies_consent.consent'].search_count([])
        self.opener.post(
            f'{self.base_url()}/muk_website_cookies_consent/consent',
            json={
                'jsonrpc': '2.0',
                'method': 'call',
                'id': 1,
                'params': {'state': 'not a dict'},
            },
        )
        self.assertEqual(
            self.env['muk_website_cookies_consent.consent'].search_count([]), before
        )
