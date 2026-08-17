import json

from odoo.tests import tagged

from odoo.addons.muk_website_cookies_consent.tests.common import CookieConsentCommon


@tagged('post_install', '-at_install')
class TestGating(CookieConsentCommon):
    """The purpose gating matrix, which everything else depends on."""

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_no_cookie_grants_only_essential(self):
        self.patch_request()
        self.assertEqual(self.website._get_granted_cookie_codes(), {'essential'})
        self.assertFalse(self.website._has_cookie_decision())

    def test_essential_is_always_granted(self):
        self.patch_request()
        self.assertTrue(self.website._is_cookie_category_granted('essential'))

    def test_granting_analytics_does_not_grant_marketing(self):
        self.patch_request(self.build_cookie(['analytics']))
        self.assertTrue(self.website._is_cookie_category_granted('analytics'))
        self.assertFalse(self.website._is_cookie_category_granted('marketing'))

    def test_accept_all_grants_every_purpose_on_offer(self):
        codes = self.website._get_offered_cookie_categories().mapped('code')
        self.patch_request(self.build_cookie(codes))
        for code in codes:
            self.assertTrue(self.website._is_cookie_category_granted(code), code)
        self.assertTrue(self.website._allConsentsGranted())

    def test_partial_consent_is_not_full_consent(self):
        self.patch_request(self.build_cookie(['analytics']))
        self.assertFalse(self.website._allConsentsGranted())

    def test_malformed_cookie_is_treated_as_no_decision(self):
        self.patch_request('not json at all')
        self.assertFalse(self.website._has_cookie_decision())
        self.assertEqual(self.website._get_granted_cookie_codes(), {'essential'})

    def test_unknown_payload_version_is_ignored(self):
        self.patch_request('{"v": 99, "cats": ["marketing"], "ts": 1}')
        self.assertFalse(self.website._has_cookie_decision())
        self.assertFalse(self.website._is_cookie_category_granted('marketing'))

    def test_raising_the_policy_version_invalidates_consent(self):
        cookie = self.build_cookie(['analytics'])
        self.website.cookie_policy_version = 2
        self.patch_request(cookie)
        self.assertFalse(self.website._has_cookie_decision())
        self.assertFalse(self.website._is_cookie_category_granted('analytics'))

    def test_changing_the_registry_invalidates_consent(self):
        cookie = self.build_cookie(['analytics'])
        self.env['muk_website_cookies_consent.cookie'].create(
            {
                'name': '_newly_declared',
                'category_id': self.category_analytics.id,
                'storage_type': 'http',
            }
        )
        self.patch_request(cookie)
        self.assertFalse(
            self.website._has_cookie_decision(),
            'A newly declared cookie must invalidate an earlier decision.',
        )

    def test_expired_consent_is_not_relied_on(self):
        self.patch_request()
        lifetime = self.website._get_cookie_lifetime_days()
        self.patch_request(self.build_cookie(['analytics'], age_days=lifetime + 1))
        self.assertFalse(self.website._has_cookie_decision())

    def test_consent_within_its_lifetime_still_counts(self):
        self.patch_request()
        lifetime = self.website._get_cookie_lifetime_days()
        self.patch_request(
            self.build_cookie(['analytics'], age_days=max(lifetime - 1, 0))
        )
        self.assertTrue(self.website._has_cookie_decision())

    def test_the_region_rule_decides_the_lifetime(self):
        self.patch_request()
        self.assertEqual(
            self.website._get_cookie_lifetime_days(),
            180,
            'An Austrian visitor gets the conservative six months, since no '
            'national figure is published.',
        )

    def test_gpc_header_refuses_everything_optional(self):
        self.patch_request(
            self.build_cookie(['analytics', 'marketing']), headers={'Sec-GPC': '1'}
        )
        self.assertEqual(self.website._get_granted_cookie_codes(), {'essential'})
        self.assertFalse(self.website._allConsentsGranted())

    def test_gpc_other_values_are_ignored(self):
        self.patch_request(self.build_cookie(['analytics']), headers={'Sec-GPC': '0'})
        self.assertTrue(self.website._is_cookie_category_granted('analytics'))

    def test_gpc_absence_never_grants_anything(self):
        self.patch_request(headers={})
        self.assertEqual(self.website._get_granted_cookie_codes(), {'essential'})

    def test_gpc_can_be_turned_off(self):
        self.website.cookie_respect_gpc = False
        self.patch_request(self.build_cookie(['analytics']), headers={'Sec-GPC': '1'})
        self.assertTrue(self.website._is_cookie_category_granted('analytics'))

    def test_core_optional_type_follows_marketing(self):
        self.patch_request(self.build_cookie(['marketing']))
        self.assertTrue(self.env['ir.http']._is_allowed_cookie('optional'))

    def test_core_optional_type_refused_without_marketing(self):
        self.patch_request(self.build_cookie(['analytics']))
        self.assertFalse(self.env['ir.http']._is_allowed_cookie('optional'))

    def test_core_required_type_is_always_allowed(self):
        self.patch_request()
        self.assertTrue(self.env['ir.http']._is_allowed_cookie('required'))

    def test_category_helper_is_exposed_on_ir_http(self):
        self.patch_request(self.build_cookie(['analytics']))
        self.assertTrue(self.env['ir.http']._is_allowed_cookie_category('analytics'))
        self.assertFalse(self.env['ir.http']._is_allowed_cookie_category('marketing'))

    def test_disabling_the_bar_falls_back_to_core(self):
        self.website.cookies_bar = False
        self.patch_request()
        self.assertFalse(self.website._is_cookie_consent_active())
        self.assertTrue(
            self.website._allConsentsGranted(),
            'With the bar off core treats consent as given, and that must not change.',
        )

    def test_contextual_service_needs_its_own_grant(self):
        self.patch_request(self.build_cookie(['marketing']))
        self.assertFalse(
            self.website._is_cookie_service_granted(self.service_youtube),
            'A purpose granted in the dialog must not enable an embed asked for in place.',
        )
        self.patch_request(self.build_cookie(['marketing'], services=['youtube']))
        self.assertTrue(self.website._is_cookie_service_granted(self.service_youtube))

    def test_non_contextual_service_follows_its_purpose(self):
        self.patch_request(self.build_cookie(['marketing']))
        self.assertTrue(self.website._is_cookie_service_granted(self.service_linkedin))

    def test_a_service_granted_on_its_own_stands_alone(self):
        self.patch_request(self.build_cookie([], services=['youtube']))
        self.assertTrue(
            self.website._is_cookie_service_granted(self.service_youtube),
            'Allowing one embed has to be enough for that embed to load.',
        )
        self.assertFalse(
            self.website._is_cookie_category_granted('marketing'),
            'But it must not grant the purpose it belongs to.',
        )

    def test_consent_mode_maps_purposes_to_signals(self):
        self.patch_request(self.build_cookie(['analytics']))
        state = self.website._get_consent_mode_state()
        self.assertEqual(state['analytics_storage'], 'granted')
        self.assertEqual(state['ad_storage'], 'denied')
        self.assertEqual(state['ad_user_data'], 'denied')
        self.assertEqual(state['ad_personalization'], 'denied')
        self.assertEqual(
            state['security_storage'],
            'granted',
            'Security storage is strictly necessary and never withheld.',
        )

    def test_consent_mode_grants_advertising_with_marketing(self):
        self.patch_request(self.build_cookie(['marketing']))
        state = self.website._get_consent_mode_state()
        for signal in ('ad_storage', 'ad_user_data', 'ad_personalization'):
            self.assertEqual(state[signal], 'granted', signal)

    def test_consent_mode_defaults_deny_before_any_decision(self):
        self.patch_request()
        defaults = self.website._get_consent_mode_default_json()
        self.assertIn('"analytics_storage": "denied"', defaults)
        self.assertIn('"wait_for_update": 500', defaults)

    def test_ads_data_redaction_tracks_ad_storage(self):
        self.patch_request()
        self.assertEqual(self.website._get_ads_data_redaction_json(), 'true')
        self.patch_request(self.build_cookie(['marketing']))
        self.assertEqual(self.website._get_ads_data_redaction_json(), 'false')

    def test_an_embed_only_record_grants_its_service_without_answering(self):
        state = self.build_cookie(['essential'], services=['youtube'])
        payload = json.loads(state)
        payload['ans'] = 0
        self.patch_request(json.dumps(payload))
        website = self.as_visitor()
        self.assertTrue(
            website._has_cookie_record(),
            'The payload is current, so the service it grants is in force.',
        )
        self.assertFalse(
            website._has_cookie_decision(),
            'Allowing an embed answers nothing, so the banner must ask again.',
        )
        self.assertIn('youtube', website._get_granted_cookie_services())

    def test_an_expired_record_grants_nothing(self):
        self.patch_request(self.build_cookie(['analytics'], age_days=9999))
        website = self.as_visitor()
        self.assertFalse(website._has_cookie_record())
        self.assertFalse(website._is_cookie_category_granted('analytics'))
