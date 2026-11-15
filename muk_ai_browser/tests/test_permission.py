from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, new_test_user


class TestPermission(TransactionCase):
    """Verify which site rule decides for a user and which sites are valid."""

    def test_the_most_specific_rule_wins_unless_everyone_is_blocked(self):
        other = new_test_user(self.env, login='browser-other')
        rules = self.env['muk_ai_browser.permission']
        rules.create(
            [
                {'site': '*.example.com', 'mode': 'ask', 'user_id': False},
                {'site': 'https://shop.example.com', 'mode': 'allow', 'user_id': False},
                {'site': 'https://mine.example.com/', 'mode': 'allow'},
                {'site': '*.mine.example.com', 'mode': 'block'},
                {'site': '*.example.org', 'mode': 'block', 'user_id': False},
                {'site': 'https://blocked.example.org', 'mode': 'allow'},
            ]
        )
        for origin, user, mode in (
            ('https://news.example.com', self.env.user, 'ask'),
            ('https://shop.example.com', self.env.user, 'allow'),
            ('https://mine.example.com', self.env.user, 'allow'),
            ('https://mine.example.com', other, 'ask'),
            ('https://a.mine.example.com', self.env.user, 'block'),
            ('https://blocked.example.org', self.env.user, 'block'),
            ('https://unknown.net', self.env.user, 'ask'),
            ('', self.env.user, 'ask'),
        ):
            with self.subTest(origin=origin, user=user.login):
                self.assertEqual(rules._mode_for(user, origin), mode)
        self.env['ir.config_parameter'].sudo().set_str(
            'muk_ai_browser.default_mode', 'block'
        )
        self.assertEqual(rules._mode_for(self.env.user, 'https://unknown.net'), 'block')

    def test_only_origins_and_domain_patterns_are_sites(self):
        rules = self.env['muk_ai_browser.permission']
        for site, valid in (
            ('https://Shop.example.com/', True),
            ('http://localhost:8069', True),
            ('*.example.com', True),
            ('example.com', False),
            ('https://example.com/path', False),
            ('ftp://example.com', False),
        ):
            with self.subTest(site=site):
                if valid:
                    rules.create({'site': site})
                else:
                    with self.assertRaises(ValidationError):
                        rules.create({'site': site})
