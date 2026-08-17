from __future__ import annotations

from odoo import models
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from odoo.addons.muk_website_cookies_consent.controllers.main import (
    CookieConsentController,
)
from odoo.addons.muk_website_cookies_consent.tests.common import CookieConsentCommon
from odoo.addons.muk_website_cookies_consent.tools.constants import (
    ESSENTIAL_CODE,
    UNCLASSIFIED_CODE,
)


@tagged('post_install', '-at_install')
class TestConsentLog(CookieConsentCommon):
    """Recording consent as proof, and the registry rules around it."""

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def log_decision(self, **overrides) -> models.Model:
        """Return the record a decision leaves behind.

        :param overrides: the values that differ from a plain custom decision
        """
        values = {
            'consent_uid': 'uid-1',
            'action': 'custom',
            'source': 'banner',
            'granted_category_ids': [(6, 0, self.category_analytics.ids)],
            'denied_category_ids': [(6, 0, self.category_marketing.ids)],
            'policy_version': 1,
            'registry_hash': 'abcdef123456',
        }
        values.update(overrides)
        return self.env['muk_website_cookies_consent.consent']._log_decision(
            self.website, values
        )

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_a_decision_is_recorded(self):
        self.patch_request()
        record = self.log_decision()
        self.assertTrue(record)
        self.assertEqual(record.action, 'custom')
        self.assertEqual(record.granted_category_ids, self.category_analytics)

    def test_refusals_are_recorded_too(self):
        self.patch_request()
        record = self.log_decision()
        self.assertEqual(
            record.denied_category_ids,
            self.category_marketing,
            'A refusal is evidence and has to be stored explicitly.',
        )

    def test_recording_can_be_turned_off(self):
        self.website.cookie_log_consent = False
        self.patch_request()
        self.assertFalse(self.log_decision())

    def test_ip_is_stored_as_a_salted_hash(self):
        self.patch_request()
        record = self.log_decision()
        self.assertTrue(record.ip_hash)
        self.assertEqual(len(record.ip_hash), 64)
        self.assertNotIn('81.223.45', record.ip_hash)

    def test_ip_hash_can_be_turned_off_on_its_own(self):
        self.website.cookie_log_ip = False
        self.patch_request()
        self.assertFalse(self.log_decision().ip_hash)

    def test_ipv4_is_truncated_to_its_network(self):
        model = self.env['muk_website_cookies_consent.consent']
        self.assertEqual(model._truncate_ip('81.223.45.67'), '81.223.45.0/24')

    def test_ipv6_is_truncated_to_its_network(self):
        model = self.env['muk_website_cookies_consent.consent']
        self.assertEqual(
            model._truncate_ip('2001:db8:85a3::8a2e:370:7334'), '2001:db8:85a3::/64'
        )

    def test_a_bad_address_hashes_to_nothing(self):
        model = self.env['muk_website_cookies_consent.consent']
        self.assertEqual(model._truncate_ip('not an address'), '')
        self.assertEqual(model._hash_ip('not an address'), '')

    def test_the_same_network_hashes_consistently(self):
        model = self.env['muk_website_cookies_consent.consent']
        self.assertEqual(
            model._hash_ip('81.223.45.67'),
            model._hash_ip('81.223.45.99'),
            'Two addresses in one /24 must be indistinguishable in the log.',
        )

    def test_different_networks_hash_differently(self):
        model = self.env['muk_website_cookies_consent.consent']
        self.assertNotEqual(
            model._hash_ip('81.223.45.67'), model._hash_ip('81.223.46.67')
        )

    def test_a_failed_write_never_raises(self):
        self.patch_request()
        self.assertFalse(
            self.log_decision(action='not-a-valid-action'),
            'Recording must never be able to break the visitor’s consent.',
        )

    def test_purge_removes_only_expired_records(self):
        self.patch_request()
        fresh = self.log_decision()
        stale = self.log_decision(consent_uid='uid-old')
        table = self.env['muk_website_cookies_consent.consent']._table
        self.env.cr.execute(
            f'UPDATE {table} SET create_date = now() - interval %s WHERE id = %s',
            ('4 years', stale.id),
        )
        stale.invalidate_recordset()
        self.env['muk_website_cookies_consent.consent']._cron_purge_records()
        self.assertTrue(fresh.exists())
        self.assertFalse(stale.exists())

    def test_a_non_essential_purpose_cannot_be_pre_selected(self):
        with self.assertRaises(ValidationError):
            self.category_analytics.default_enabled = True

    def test_an_essential_purpose_may_be_pre_selected(self):
        self.category_essential.default_enabled = True
        self.assertTrue(self.category_essential.default_enabled)

    def test_unknown_consent_mode_signals_are_refused(self):
        with self.assertRaises(ValidationError):
            self.category_analytics.consent_mode_signals = 'analytics_storage nonsense'

    def test_the_essential_code_is_reserved(self):
        with self.assertRaises(ValidationError):
            self.env['muk_website_cookies_consent.category'].create(
                {'name': 'Impostor', 'code': 'essential'}
            )

    def test_registry_hash_changes_with_the_registry(self):
        before = self.website._get_cookie_registry_hash()
        self.env['muk_website_cookies_consent.service'].create(
            {
                'name': 'Some Tracker',
                'technical_name': 'some_tracker',
                'category_id': self.category_analytics.id,
                'domains': 'tracker.example.com',
            }
        )
        self.assertNotEqual(
            before,
            self.website._get_cookie_registry_hash(),
            'The fingerprint must move when the disclosure moves.',
        )

    def test_registry_hash_is_stable_otherwise(self):
        self.assertEqual(
            self.website._get_cookie_registry_hash(),
            self.website._get_cookie_registry_hash(),
        )

    def test_a_code_with_a_separator_is_refused(self):
        with self.assertRaises(ValidationError):
            self.env['muk_website_cookies_consent.category'].create(
                {'name': 'Bad', 'code': 'ads,marketing'}
            )

    def test_a_service_name_with_a_separator_is_refused(self):
        with self.assertRaises(ValidationError):
            self.env['muk_website_cookies_consent.service'].create(
                {
                    'name': 'Bad',
                    'technical_name': 'a,b',
                    'category_id': self.category_analytics.id,
                }
            )

    def test_a_record_cannot_be_changed(self):
        record = self.env['muk_website_cookies_consent.consent']._log_decision(
            self.website,
            {
                'consent_uid': 'immutable-uid',
                'action': 'accept_all',
                'source': 'banner',
                'policy_version': 1,
                'registry_hash': 'abc123abc123',
            },
        )
        with self.assertRaises(UserError):
            record.action = 'reject_all'

    def test_a_record_cannot_be_deleted_outside_the_purge(self):
        record = self.env['muk_website_cookies_consent.consent']._log_decision(
            self.website,
            {
                'consent_uid': 'undeletable-uid',
                'action': 'accept_all',
                'source': 'banner',
                'policy_version': 1,
                'registry_hash': 'abc123abc123',
            },
        )
        with self.assertRaises(UserError):
            record.unlink()
        record.with_context(cookie_consent_purge=True).unlink()
        self.assertFalse(record.exists())

    def test_only_offered_purposes_can_be_refused(self):
        self.patch_request()
        granted, denied = CookieConsentController()._resolve_categories(
            self.website, ['analytics']
        )
        offered = self.website._get_offered_cookie_categories()
        self.assertEqual(granted | denied, offered)
        self.assertNotIn(
            UNCLASSIFIED_CODE,
            denied.mapped('code'),
            'A purpose the dialog never showed was not declined by anyone.',
        )

    def test_an_unanswered_payload_refuses_nothing(self):
        self.patch_request()
        granted, denied = CookieConsentController()._resolve_categories(
            self.website, ['essential'], answered=False
        )
        self.assertFalse(
            denied,
            'Allowing an embed in place answers no purpose, so filing every '
            'other one as refused would invent decisions the visitor never took.',
        )
        self.assertEqual(granted.mapped('code'), [ESSENTIAL_CODE])
