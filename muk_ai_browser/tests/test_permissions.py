from odoo.addons.muk_ai_browser.tests.common import BrowserTestCommon


class TestPermissions(BrowserTestCommon):
    """Verify per-site permission mode resolution and granting."""

    def test_default_mode_is_ask(self):
        permission = self.env['muk_ai_browser.permission']
        self.assertEqual(
            permission._mode_for(self.env.user, 'https://shop.example'),
            'ask',
        )

    def test_grant_sets_follow_plan(self):
        permission = self.env['muk_ai_browser.permission']
        granted = permission._grant(self.env.user, 'https://shop.example')
        self.assertEqual(granted.mode, 'follow_plan')
        self.assertEqual(
            permission._mode_for(self.env.user, 'https://shop.example'),
            'follow_plan',
        )

    def test_grant_is_idempotent_per_origin(self):
        permission = self.env['muk_ai_browser.permission']
        first = permission._grant(self.env.user, 'https://shop.example')
        second = permission._grant(self.env.user, 'https://shop.example')
        self.assertEqual(first, second)
        self.assertEqual(
            permission.search_count(
                [
                    ('user_id', '=', self.env.user.id),
                    ('origin', '=', 'https://shop.example'),
                ],
            ),
            1,
        )

    def test_grant_is_origin_scoped(self):
        permission = self.env['muk_ai_browser.permission']
        permission._grant(self.env.user, 'https://shop.example')
        self.assertEqual(
            permission._mode_for(self.env.user, 'https://other.example'),
            'ask',
        )

    def test_missing_origin_stays_ask(self):
        permission = self.env['muk_ai_browser.permission']
        self.assertEqual(permission._mode_for(self.env.user, None), 'ask')
        self.assertEqual(permission._mode_for(self.env.user, ''), 'ask')
