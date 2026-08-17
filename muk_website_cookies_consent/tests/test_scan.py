from __future__ import annotations

from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.muk_website_cookies_consent.models import website as website_model
from odoo.addons.muk_website_cookies_consent.tests.common import CookieConsentCommon
from odoo.addons.muk_website_cookies_consent.tools.consent import (
    is_current,
    parse_state,
)
from odoo.addons.muk_website_cookies_consent.tools.scanner import (
    extract_hosts,
    extract_keys,
)

PAGE = """
<html><head>
    <script src="https://connect.facebook.net/en_US/fbevents.js"></script>
    <script src="/web/static/src/own.js"></script>
    <link rel="stylesheet" href="https://fonts.googleapis.com/css?family=Roboto"/>
    <script>
        localStorage.setItem('ajs_anonymous_id', '1');
        sessionStorage.setItem("cart_hint", "x");
        document.cookie = '_hjSession=1; path=/';
    </script>
</head><body>
    <iframe src="//player.vimeo.com/video/1"></iframe>
    <img src="https://www.example.org/pixel.gif"/>
    <script src="about:blank" data-nocookie-src="https://snap.licdn.com/li.js"></script>
</body></html>
"""


@tagged('post_install', '-at_install')
class TestScanExtraction(CookieConsentCommon):
    """Reading a fetched page for what it sets and loads."""

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_third_party_hosts_are_read_off_every_carrier(self):
        hosts = extract_hosts(PAGE, {'example.com'})
        self.assertEqual(
            hosts,
            {
                'connect.facebook.net',
                'fonts.googleapis.com',
                'player.vimeo.com',
                'example.org',
                'snap.licdn.com',
            },
        )

    def test_a_blocked_source_still_names_its_host(self):
        markup = '<script src="about:blank" data-nocookie-src="https://x.test/a.js"/>'
        self.assertEqual(extract_hosts(markup, set()), {'x.test'})

    def test_the_sites_own_host_is_not_a_third_party(self):
        markup = '<script src="https://www.example.com/a.js"></script>'
        self.assertFalse(extract_hosts(markup, {'example.com'}))

    def test_a_relative_source_names_no_host(self):
        self.assertFalse(extract_hosts('<script src="/web/a.js"/>', set()))

    def test_storage_keys_come_from_the_scripts_that_write_them(self):
        keys = extract_keys(PAGE, {'example.com'}, '/')
        self.assertIn({'name': 'ajs_anonymous_id', 'type': 'local', 'url': '/'}, keys)
        self.assertIn({'name': 'cart_hint', 'type': 'session', 'url': '/'}, keys)

    def test_a_cookie_set_by_script_is_found(self):
        keys = extract_keys(PAGE, {'example.com'}, '/shop')
        self.assertIn({'name': '_hjSession', 'type': 'http', 'url': '/shop'}, keys)

    def test_rubbish_markup_yields_nothing(self):
        self.assertFalse(extract_hosts('', set()))
        self.assertFalse(extract_keys('', set(), '/'))


@tagged('post_install', '-at_install')
class TestScanCrawl(CookieConsentCommon):
    """Walking the site's own pages without leaving the process."""

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def patch_fetch(self, pages: dict) -> list[str]:
        """Serve the given markup per URL and record what was asked for.

        :param pages: markup by absolute URL suffix, missing ones failing
        :return: the URLs the scan fetched, in order
        """
        asked = []

        def fetch(website, session, url):
            asked.append(url)
            for suffix, markup in pages.items():
                if url.endswith(suffix):
                    return markup
            return ''

        self.patch(website_model.Website, '_fetch_cookie_scan_page', fetch)
        return asked

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_the_home_page_is_always_scanned_first(self):
        urls = self.website._get_cookie_scan_urls()
        self.assertEqual(urls[0], '/')

    def test_the_page_limit_is_respected(self):
        self.website.cookie_scan_pages = 2
        self.assertEqual(len(self.website._get_cookie_scan_urls()), 2)

    def test_the_scan_browses_as_a_visitor_who_allowed_everything(self):
        state = parse_state(self.website._get_cookie_scan_consent())
        self.assertTrue(
            is_current(
                state,
                self.website.cookie_policy_version,
                self.website._get_cookie_registry_hash(),
                self.website._get_cookie_lifetime_days(),
            ),
            'A payload the site would reject as stale would have the scan look '
            'at its own blocking instead of at the third parties.',
        )
        self.assertIn('analytics', state['cats'])
        self.assertIn('youtube', state['svcs'])

    def test_a_scan_files_what_the_pages_reveal(self):
        self.website.cookie_scan_pages = 1
        self.patch_fetch({'/': PAGE})
        result = self.website._scan_cookies()
        self.assertEqual(result['pages'], 1)
        findings = self.env['muk_website_cookies_consent.observation'].search(
            [('website_id', '=', self.website.id)]
        )
        self.assertIn('connect.facebook.net', findings.mapped('name'))
        self.assertIn('ajs_anonymous_id', findings.mapped('name'))
        self.assertEqual(self.website.cookie_scan_count, 1)
        self.assertTrue(self.website.cookie_scan_date)

    def test_a_page_that_does_not_answer_is_counted_and_skipped(self):
        self.website.cookie_scan_pages = 2
        self.patch_fetch({})
        result = self.website._scan_cookies()
        self.assertEqual(result['pages'], 0)
        self.assertEqual(result['failures'], 2)

    def test_a_scan_that_reaches_nothing_says_so(self):
        self.website.cookie_scan_pages = 1
        self.patch_fetch({})
        with self.assertRaises(UserError):
            self.website.action_cookie_scan()

    def test_a_free_website_takes_its_scan_lock(self):
        self.assertTrue(self.website._lock_cookie_scan())

    def test_a_scan_stands_down_while_another_one_holds_the_lock(self):
        self.website.cookie_scan_pages = 1
        self.website.cookie_scan_date = '2026-01-01 00:00:00'
        asked = self.patch_fetch({'/': PAGE})
        self.patch(website_model.Website, '_lock_cookie_scan', lambda website: False)
        result = self.website._scan_cookies()
        self.assertEqual(result, {'pages': 0, 'keys': 0, 'failures': 0, 'running': 1})
        self.assertFalse(
            asked,
            'The weekly cron and a Scan Now click can land together, and '
            'Postgres ends a race between them by killing one of the two.',
        )
        self.assertEqual(
            str(self.website.cookie_scan_date),
            '2026-01-01 00:00:00',
            'A scan that never ran must not claim the site was just looked at.',
        )

    def test_a_declared_host_is_filed_without_asking_for_review(self):
        self.website.cookie_scan_pages = 1
        self.patch_fetch({'/': '<iframe src="https://www.youtube.com/embed/x"/>'})
        self.website._scan_cookies()
        finding = self.env['muk_website_cookies_consent.observation'].search(
            [('name', '=', 'youtube.com'), ('website_id', '=', self.website.id)]
        )
        self.assertEqual(finding.state, 'declared')
