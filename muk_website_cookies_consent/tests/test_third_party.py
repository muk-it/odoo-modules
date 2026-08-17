from odoo.tests import tagged

from odoo.addons.muk_website_cookies_consent.tests.common import CookieConsentCommon
from odoo.addons.muk_website_cookies_consent.tools.constants import (
    CONSENT_MODE_HOSTS,
)

YOUTUBE_IFRAME = (
    '<div><iframe src="https://www.youtube.com/embed/abc123"></iframe></div>'
)
LINKEDIN_SCRIPT = '<div><script src="https://snap.licdn.com/li.lms-analytics/insight.min.js"></script></div>'
OWN_SCRIPT = '<div><script src="/web/static/src/legacy.js"></script></div>'
UNCLAIMED_IFRAME = '<div><iframe src="https://www.youku.com/embed/x"></iframe></div>'
PASTED_SNIPPET = (
    '<!-- Meta Pixel -->\n'
    '<script src="https://connect.facebook.net/en_US/fbevents.js"></script>\n'
    '<meta name="pasted" content="1"/>'
)


@tagged('post_install', '-at_install')
class TestThirdParty(CookieConsentCommon):
    """Per-service stripping of third-party scripts and embeds."""

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_service_matches_its_own_host(self):
        self.assertTrue(
            self.service_youtube._matches_url('https://www.youtube.com/embed/x')
        )
        self.assertTrue(self.service_youtube._matches_url('https://youtu.be/x'))

    def test_service_matches_subdomains(self):
        self.assertTrue(
            self.service_youtube._matches_url('https://player.youtube.com/embed/x')
        )

    def test_service_does_not_match_a_lookalike_host(self):
        self.assertFalse(
            self.service_youtube._matches_url('https://notyoutube.com/embed/x'),
            'A suffix match must not treat notyoutube.com as youtube.com.',
        )

    def test_host_and_path_pattern_narrows_a_shared_host(self):
        maps = self.env.ref('muk_website_cookies_consent.service_google_maps')
        self.assertTrue(
            maps._matches_url('https://www.google.com/maps/embed?pb=1'),
            'A map embed on a shared Google host must still be recognised.',
        )
        self.assertFalse(
            maps._matches_url('https://www.google.com/recaptcha/api.js'),
            'A path pattern must not gate everything else on the same host.',
        )

    def test_pasted_custom_code_is_scrubbed_without_being_rewritten(self):
        self.patch_request()
        controlled = self.as_visitor()._control_third_party_trackers_in_html(
            PASTED_SNIPPET
        )
        self.assertIn('about:blank', controlled)
        self.assertIn(
            '<!-- Meta Pixel -->',
            controlled,
            'What an admin pastes is a fragment, and parsing it as a document '
            'drops the comment in front of the tag.',
        )
        self.assertNotIn(
            '<html>',
            controlled,
            'A wrapper closes the real head early, and the browser recovers '
            'the rest of the page as body content.',
        )
        self.assertIn(
            '<meta name="pasted"',
            controlled,
            'Everything the admin pasted has to survive, not just the first '
            'element of it.',
        )

    def test_embed_is_stripped_without_consent(self):
        self.patch_request()
        html = self.as_visitor()._control_third_party_trackers_in_html(YOUTUBE_IFRAME)
        self.assertIn('about:blank', html)
        self.assertIn('data-need-cookies-approval', html)
        self.assertIn('data-nocookie-src', html)

    def test_stripped_embed_carries_the_purpose_that_releases_it(self):
        self.patch_request()
        html = self.as_visitor()._control_third_party_trackers_in_html(YOUTUBE_IFRAME)
        self.assertIn('data-muk-cookie-category="marketing"', html)
        self.assertIn('data-muk-cookie-service="youtube"', html)

    def test_embed_survives_once_its_service_is_granted(self):
        self.patch_request(self.build_cookie(['marketing'], services=['youtube']))
        html = self.as_visitor()._control_third_party_trackers_in_html(YOUTUBE_IFRAME)
        self.assertNotIn('about:blank', html)
        self.assertIn('youtube.com/embed/abc123', html)

    def test_one_purpose_does_not_release_another(self):
        self.patch_request(self.build_cookie(['analytics']))
        html = self.as_visitor()._control_third_party_trackers_in_html(LINKEDIN_SCRIPT)
        self.assertIn(
            'about:blank',
            html,
            'Granting statistics must not release a marketing tracker.',
        )

    def test_granting_marketing_releases_its_script(self):
        self.patch_request(self.build_cookie(['marketing']))
        html = self.as_visitor()._control_third_party_trackers_in_html(LINKEDIN_SCRIPT)
        self.assertNotIn('about:blank', html)

    def test_first_party_scripts_are_never_touched(self):
        self.patch_request()
        html = self.as_visitor()._control_third_party_trackers_in_html(OWN_SCRIPT)
        self.assertNotIn('about:blank', html)
        self.assertIn('/web/static/src/legacy.js', html)

    def test_nothing_is_stripped_once_everything_is_granted(self):
        codes = self.website._get_cookie_categories().mapped('code')
        services = self.website._get_cookie_services().mapped('technical_name')
        self.patch_request(self.build_cookie(codes, services=services))
        self.assertFalse(self.as_visitor()._should_remove_third_party_trackers())

    def test_blocking_can_be_turned_off(self):
        self.website.cookie_blocking = False
        self.patch_request()
        html = self.as_visitor()._control_third_party_trackers_in_html(YOUTUBE_IFRAME)
        self.assertNotIn(
            'data-muk-cookie-category',
            html,
            'With blocking off this module must not add its own markers.',
        )

    def test_client_blocklist_narrows_to_refused_services(self):
        codes = self.website._get_cookie_categories().mapped('code')
        services = self.website._get_cookie_services().mapped('technical_name')
        self.patch_request(self.build_cookie(codes, services=services))
        self.assertEqual(
            self.website._get_blocked_third_party_domains_list(),
            [],
            'Nothing is refused, so the watcher must be handed an empty list.',
        )

    def test_client_blocklist_keeps_unclaimed_core_domains(self):
        self.patch_request(self.build_cookie(['analytics']))
        blocked = self.website._get_blocked_third_party_domains_list()
        self.assertIn(
            'youku.com',
            blocked,
            'A core-listed host no service claims stays blocked until nothing is refused.',
        )

    def test_client_blocklist_drops_a_granted_service_host(self):
        codes = self.website._get_cookie_categories().mapped('code')
        services = self.website._get_cookie_services().mapped('technical_name')
        self.patch_request(self.build_cookie(codes, services=services))
        self.assertNotIn(
            'youtube.com', self.website._get_blocked_third_party_domains_list()
        )

    def test_unclaimed_core_host_is_stripped_while_anything_is_refused(self):
        services = self.website._get_cookie_services().mapped('technical_name')
        self.patch_request(
            self.build_cookie(['functional', 'marketing'], services=services)
        )
        self.assertFalse(self.as_visitor()._get_blocked_cookie_services())
        html = self.as_visitor()._control_third_party_trackers_in_html(UNCLAIMED_IFRAME)
        self.assertIn(
            'about:blank',
            html,
            'A host no service claims belongs to no purpose, so it waits for '
            'full consent instead of slipping through.',
        )

    def test_unclaimed_core_host_loads_once_nothing_is_refused(self):
        codes = self.website._get_cookie_categories().mapped('code')
        services = self.website._get_cookie_services().mapped('technical_name')
        self.patch_request(self.build_cookie(codes, services=services))
        self.assertTrue(self.website._allConsentsGranted())
        html = self.as_visitor()._control_third_party_trackers_in_html(UNCLAIMED_IFRAME)
        self.assertNotIn(
            'about:blank',
            html,
            'With nothing refused there is nothing left to strip.',
        )

    def test_the_google_tag_is_not_stripped_once_the_visitor_has_decided(self):
        self.website.write(
            {'google_analytics_key': 'G-TESTKEY123', 'cookie_consent_mode': 'basic'}
        )
        self.patch_request(self.build_cookie(['analytics']))
        html = '<div><script src="https://www.googletagmanager.com/gtag/js?id=G-X"></script></div>'
        stripped = self.as_visitor()._control_third_party_trackers_in_html(html)
        self.assertNotIn('about:blank', stripped)
        self.assertIn('googletagmanager.com/gtag/js', stripped)

    def test_basic_mode_holds_the_google_tag_after_a_refusal(self):
        self.website.write(
            {'google_analytics_key': 'G-TESTKEY123', 'cookie_consent_mode': 'basic'}
        )
        self.patch_request(self.build_cookie([]))
        html = '<div><script src="https://www.googletagmanager.com/gtag/js?id=G-X"></script></div>'
        stripped = self.as_visitor()._control_third_party_trackers_in_html(html)
        self.assertIn(
            'about:blank',
            stripped,
            'A refusal is a decision, and the mode that holds tags until '
            'consent must hold them when consent is refused outright.',
        )

    def test_the_watcher_never_blocks_a_tag_the_server_spares(self):
        self.website.write(
            {'google_analytics_key': 'G-TESTKEY123', 'cookie_consent_mode': 'basic'}
        )
        self.patch_request(self.build_cookie(['analytics']))
        website = self.as_visitor()
        blocked = website._get_blocked_third_party_domains_list()
        for host in CONSENT_MODE_HOSTS:
            self.assertNotIn(
                host,
                blocked,
                'The watcher rewrites the src of a script created at runtime, '
                'which is how a Tag Manager container loads, so blocking it '
                'there would undo what the server deliberately spared.',
            )

    def test_the_watcher_blocks_the_google_tag_while_the_server_does(self):
        self.website.write(
            {'google_analytics_key': 'G-TESTKEY123', 'cookie_consent_mode': 'basic'}
        )
        self.patch_request()
        blocked = self.as_visitor()._get_blocked_third_party_domains_list()
        self.assertIn('googletagmanager.com', blocked)

    def test_basic_mode_holds_the_google_tag_until_the_visitor_decides(self):
        self.website.write(
            {'google_analytics_key': 'G-TESTKEY123', 'cookie_consent_mode': 'basic'}
        )
        self.patch_request()
        html = '<div><script src="https://www.googletagmanager.com/gtag/js?id=G-X"></script></div>'
        stripped = self.as_visitor()._control_third_party_trackers_in_html(html)
        self.assertIn(
            'about:blank',
            stripped,
            'Basic is sold as loading no Google tag before a decision, and a '
            'tag pasted by hand is no more exempt than one core renders.',
        )

    def test_advanced_mode_lets_the_google_tag_load_before_a_decision(self):
        self.website.write(
            {'google_analytics_key': 'G-TESTKEY123', 'cookie_consent_mode': 'advanced'}
        )
        self.patch_request()
        html = '<div><script src="https://www.googletagmanager.com/gtag/js?id=G-X"></script></div>'
        stripped = self.as_visitor()._control_third_party_trackers_in_html(html)
        self.assertNotIn(
            'about:blank',
            stripped,
            'Advanced exists to send cookieless pings before consent, which '
            'cannot happen if the tag carrying the denied state is removed.',
        )

    def test_the_google_tag_is_stripped_when_no_signal_is_emitted(self):
        self.website.write(
            {'google_analytics_key': False, 'cookie_consent_mode': 'basic'}
        )
        self.patch_request()
        html = '<div><script src="https://www.googletagmanager.com/gtag/js?id=G-X"></script></div>'
        stripped = self.as_visitor()._control_third_party_trackers_in_html(html)
        self.assertIn(
            'about:blank',
            stripped,
            "The consent state is written inside core's key guard, so with no "
            'key a spared tag would run against no signal at all.',
        )

    def test_the_google_tag_is_stripped_when_consent_mode_is_off(self):
        self.website.cookie_consent_mode = 'off'
        self.patch_request()
        html = '<div><script src="https://www.googletagmanager.com/gtag/js?id=G-X"></script></div>'
        stripped = self.as_visitor()._control_third_party_trackers_in_html(html)
        self.assertIn(
            'about:blank',
            stripped,
            'With no signalling there is nothing to carry, so the tag waits.',
        )

    def test_allowing_one_embed_does_not_grant_its_purpose(self):
        self.patch_request(self.build_cookie([], services=['youtube']))
        self.assertTrue(
            self.website._is_cookie_service_granted(self.service_youtube),
            'The embed the visitor allowed has to load.',
        )
        self.assertFalse(
            self.website._is_cookie_category_granted('marketing'),
            'Allowing one video must not grant marketing.',
        )
        self.assertFalse(
            self.website._is_cookie_service_granted(self.service_linkedin),
            'And it must not release the other services in that purpose.',
        )
        state = self.website._get_consent_mode_state()
        self.assertEqual(state['ad_storage'], 'denied')

    def test_a_declaration_deleted_behind_the_cache_does_not_break_the_page(self):
        cookie = self.env['muk_website_cookies_consent.cookie'].create(
            {
                'name': 'stale_key',
                'category_id': self.category_analytics.id,
                'storage_type': 'http',
            }
        )
        self.assertIn(cookie, self.website._get_cookie_declarations())
        self.env.cr.execute(
            'DELETE FROM muk_website_cookies_consent_cookie WHERE id = %s',
            [cookie.id],
        )
        self.env.invalidate_all()
        declarations = self.website._get_cookie_declarations()
        self.assertNotIn(
            cookie.id,
            declarations.ids,
            'Deleted straight through SQL, so the memoised id list still holds '
            'it, exactly as after a deletion in another process or a restore.',
        )
        self.assertTrue(
            declarations.mapped('name'),
            'A vanished declaration must not take every page down with it.',
        )
        self.assertTrue(self.website._get_cookie_registry_hash())

    def test_the_registry_is_not_read_once_per_element_after_a_decision(self):
        self.patch_request(self.build_cookie(['analytics'], services=['youtube']))
        website = self.as_visitor()
        website._should_remove_third_party_trackers()
        website._is_tag_domains_watchlisted(
            'iframe', {'src': 'https://www.youtube.com/embed/x'}
        )
        with self.assertQueryCount(0):
            for _ in range(50):
                website._should_remove_third_party_trackers()
                website._is_tag_domains_watchlisted(
                    'iframe', {'src': 'https://www.youtube.com/embed/x'}
                )

    def test_the_registry_is_not_read_once_per_element(self):
        self.patch_request()
        website = self.as_visitor()
        website._should_remove_third_party_trackers()
        website._is_tag_domains_watchlisted(
            'iframe', {'src': 'https://www.youtube.com/embed/x'}
        )
        with self.assertQueryCount(0):
            for _ in range(50):
                website._should_remove_third_party_trackers()
                website._is_tag_domains_watchlisted(
                    'iframe', {'src': 'https://www.youtube.com/embed/x'}
                )
