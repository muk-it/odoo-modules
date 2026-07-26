from __future__ import annotations

from odoo.tests import tagged
from odoo.tests.common import HttpCase, new_test_user


@tagged('post_install', '-at_install')
class TestWebClientLayout(HttpCase):
    """Cover the sidebar body class injected into the web client bootstrap."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.user = new_test_user(
            cls.env,
            login='appsbar_layout',
            password='appsbar_layout',
            groups='base.group_user',
        )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _get_webclient_body(self) -> str:
        """Return the rendered web client bootstrap page for the test user."""
        self.authenticate('appsbar_layout', 'appsbar_layout')
        response = self.url_open('/odoo', timeout=120)
        self.assertEqual(response.status_code, 200)
        return response.text

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_body_class_follows_sidebar_type(self):
        self.user.sidebar_type = 'small'
        self.assertIn('mk_sidebar_type_small', self._get_webclient_body())
        self.user.sidebar_type = 'invisible'
        self.assertIn('mk_sidebar_type_invisible', self._get_webclient_body())

    def test_body_class_keeps_core_classes(self):
        self.user.sidebar_type = 'large'
        body = self._get_webclient_body()
        self.assertIn('mk_sidebar_type_large', body)
        self.assertIn('o_web_client', body)
