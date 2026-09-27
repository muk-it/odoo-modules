from odoo.tests import HttpCase, new_test_user


class TestWebClientLayout(HttpCase):
    """Cover the sidebar body class injected into the web client bootstrap."""

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_body_class_follows_sidebar_type(self):
        user = new_test_user(
            self.env,
            login='appsbar_layout',
            password='appsbar_layout',
            groups='base.group_user',
        )
        self.authenticate('appsbar_layout', 'appsbar_layout')
        for sidebar_type in ('small', 'invisible', 'large'):
            with self.subTest(sidebar_type=sidebar_type):
                user.sidebar_type = sidebar_type
                body = self.url_open('/odoo', timeout=120).text
                self.assertIn(f'mk_sidebar_type_{sidebar_type}', body)
                self.assertIn('o_web_client', body)
