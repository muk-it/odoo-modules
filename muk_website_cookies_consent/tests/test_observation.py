from __future__ import annotations

from odoo import models
from odoo.tests import tagged

from odoo.addons.muk_website_cookies_consent.tests.common import CookieConsentCommon


@tagged('post_install', '-at_install')
class TestObservation(CookieConsentCommon):
    """Filing the cookies, storage keys and hosts a scan finds."""

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def capture(self, keys: list) -> models.Model:
        """Return the findings filed for a batch of scanned keys."""
        return self.env['muk_website_cookies_consent.observation']._record_keys(
            self.website, keys
        )

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_an_undeclared_cookie_waits_to_be_reviewed(self):
        found = self.capture([{'name': '_hjSession', 'type': 'http', 'url': '/shop'}])
        self.assertEqual(len(found), 1)
        self.assertEqual(found.state, 'new')
        self.assertEqual(found.sample_url, '/shop')

    def test_a_declared_cookie_is_filed_as_declared(self):
        declared = self.website._get_cookie_declarations()[0]
        found = self.capture([{'name': declared.name, 'type': 'http'}])
        self.assertEqual(
            found.state,
            'declared',
            'A scan records what the site does, so a covered key belongs on '
            'the list as evidence that the declaration matches something.',
        )

    def test_a_pattern_covers_the_family_it_declares(self):
        self.env['muk_website_cookies_consent.cookie'].create(
            {
                'name': '_ga',
                'pattern': '^_ga',
                'category_id': self.category_analytics.id,
                'storage_type': 'http',
            }
        )
        found = self.capture([{'name': '_ga_ABC123', 'type': 'http'}])
        self.assertEqual(found.state, 'declared')

    def test_a_claimed_host_is_filed_as_declared(self):
        found = self.capture([{'name': 'youtube.com', 'type': 'host'}])
        self.assertEqual(found.state, 'declared')

    def test_an_unclaimed_host_waits_to_be_reviewed(self):
        found = self.capture([{'name': 'cdn.example.org', 'type': 'host'}])
        self.assertEqual(found.storage_type, 'host')
        self.assertEqual(found.state, 'new')

    def test_seeing_a_key_again_only_counts_it(self):
        first = self.capture([{'name': 'ajs_anonymous_id', 'type': 'local'}])
        again = self.capture([{'name': 'ajs_anonymous_id', 'type': 'local'}])
        self.assertEqual(first, again)
        self.assertEqual(again.hit_count, 2)

    def test_a_finding_turns_declared_when_the_registry_catches_up(self):
        found = self.capture([{'name': '_hjSession', 'type': 'http'}])
        self.env['muk_website_cookies_consent.cookie'].create(
            {
                'name': '_hjSession',
                'category_id': self.category_analytics.id,
                'storage_type': 'http',
            }
        )
        self.assertEqual(
            found.state,
            'declared',
            'Declaring the key elsewhere answers the review, so the list must '
            'not keep asking for it until the next scan.',
        )

    def test_a_finding_returns_to_review_when_its_declaration_goes(self):
        declaration = self.env['muk_website_cookies_consent.cookie'].create(
            {
                'name': '_hjSession',
                'category_id': self.category_analytics.id,
                'storage_type': 'http',
            }
        )
        found = self.capture([{'name': '_hjSession', 'type': 'http'}])
        declaration.unlink()
        self.assertEqual(
            found.state,
            'new',
            'Withdrawing the declaration leaves the key uncovered again, and '
            'the site still sets it.',
        )

    def test_an_ignored_key_stays_ignored_when_it_is_declared(self):
        found = self.capture([{'name': 'ignored_key', 'type': 'http'}])
        found.action_ignore()
        self.env['muk_website_cookies_consent.cookie'].create(
            {
                'name': 'ignored_key',
                'category_id': self.category_analytics.id,
                'storage_type': 'http',
            }
        )
        self.assertEqual(
            found.state,
            'ignored',
            'A decision somebody took is a record, not a state of the registry.',
        )

    def test_an_ignored_key_does_not_come_back_as_new(self):
        found = self.capture([{'name': 'ignored_key', 'type': 'http'}])
        found.action_ignore()
        self.capture([{'name': 'ignored_key', 'type': 'http'}])
        self.assertEqual(found.state, 'ignored')

    def test_reopening_reads_the_registry_rather_than_asking_again(self):
        declared = self.website._get_cookie_declarations()[0]
        found = self.capture([{'name': declared.name, 'type': 'http'}])
        found.action_ignore()
        found.action_reopen()
        self.assertEqual(
            found.state,
            'declared',
            'Taking an ignore back asks the registry what the state is; it '
            'does not put a covered key up for review.',
        )

    def test_rubbish_is_dropped(self):
        self.assertFalse(
            self.capture(
                [
                    {'name': '', 'type': 'http'},
                    {'name': 'x', 'type': 'nonsense'},
                    'not a dict',
                ]
            )
        )

    def test_a_batch_is_bounded(self):
        keys = [{'name': f'key_{index}', 'type': 'http'} for index in range(250)]
        self.assertEqual(len(self.capture(keys)), 200)

    def test_declaring_files_it_under_unclassified(self):
        found = self.capture([{'name': '_hjSession', 'type': 'http'}])
        found.action_declare()
        self.assertEqual(found.state, 'declared')
        self.assertEqual(found.cookie_id.category_id.code, 'unclassified')
        self.assertEqual(found.cookie_id.name, '_hjSession')

    def test_declaring_a_host_creates_a_service_that_claims_it(self):
        found = self.capture([{'name': 'cdn.example.org', 'type': 'host'}])
        found.action_declare()
        self.assertTrue(found.service_id)
        self.assertEqual(found.service_id.technical_name, 'cdn_example_org')
        self.assertTrue(found.service_id._matches_url('https://cdn.example.org/x.js'))

    def test_a_declared_host_is_gated_from_then_on(self):
        found = self.capture([{'name': 'cdn.example.org', 'type': 'host'}])
        found.action_declare()
        self.patch_request()
        html = '<div><script src="https://cdn.example.org/x.js"></script></div>'
        stripped = self.as_visitor()._control_third_party_trackers_in_html(html)
        self.assertIn(
            'about:blank',
            stripped,
            'Once declared, an unclassified host waits for consent like any other.',
        )

    def test_a_declared_capture_is_never_put_to_the_visitor(self):
        found = self.capture([{'name': '_hjSession', 'type': 'http'}])
        found.action_declare()
        offered = self.website._get_offered_cookie_categories().mapped('code')
        self.assertNotIn(
            'unclassified',
            offered,
            'A purpose the dialog cannot describe must not be asked about.',
        )

    def test_an_unclassified_purpose_cannot_be_granted(self):
        found = self.capture([{'name': 'cdn.example.org', 'type': 'host'}])
        found.action_declare()
        codes = self.website._get_cookie_categories().mapped('code')
        self.patch_request(self.build_cookie(codes))
        self.assertFalse(
            self.as_visitor()._is_cookie_category_granted('unclassified'),
            'Even a hand-made cookie claiming it must not release it.',
        )
        self.assertIn(
            found.service_id,
            self.as_visitor()._get_blocked_cookie_services(),
            'Its service stays blocked until somebody classifies it.',
        )

    def test_capturing_does_not_invalidate_stored_consent(self):
        before = self.website._get_cookie_registry_hash()
        self.capture([{'name': '_hjSession', 'type': 'http'}])
        self.assertEqual(
            self.website._get_cookie_registry_hash(),
            before,
            'A scan must never re-ask the whole audience for consent.',
        )

    def test_declaring_does_invalidate_stored_consent(self):
        found = self.capture([{'name': '_hjSession', 'type': 'http'}])
        before = self.website._get_cookie_registry_hash()
        found.action_declare()
        self.assertNotEqual(
            self.website._get_cookie_registry_hash(),
            before,
            'A new declaration changes the disclosure, so consent has to be renewed.',
        )
