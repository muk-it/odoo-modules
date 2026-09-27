from __future__ import annotations

from odoo.tests import HttpCase, new_test_user
from odoo.tools import BinaryBytes


class TestWebClient(HttpCase):
    """Cover the company favicon and the background image session flags."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        """Create the two companies and the user the tests run as."""
        super().setUpClass()
        cls.company_a = cls.env.company
        cls.company_b = cls.env['res.company'].create({'name': 'Theme Co B'})
        cls.user = new_test_user(
            cls.env,
            login='ee_theme_user',
            password='ee_theme_user',
            groups='base.group_user',
            company_id=cls.company_b.id,
            company_ids=[(6, 0, [cls.company_a.id, cls.company_b.id])],
        )

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_session_info_flags_reflect_the_company_images(self):
        self.company_a.background_image_light = BinaryBytes(b'light')
        self.company_a.background_image_dark = False
        self.company_b.background_image_light = False
        self.company_b.background_image_dark = BinaryBytes(b'dark')
        self.authenticate('ee_theme_user', 'ee_theme_user')
        info = self.make_jsonrpc_request('/web/session/get_session_info', {})
        allowed = info['user_companies']['allowed_companies']
        company_a = allowed[str(self.company_a.id)]
        company_b = allowed[str(self.company_b.id)]
        self.assertTrue(company_a['has_background_image_light'])
        self.assertFalse(company_a['has_background_image_dark'])
        self.assertFalse(company_b['has_background_image_light'])
        self.assertTrue(company_b['has_background_image_dark'])

    def test_web_client_uses_the_current_company_favicon(self):
        self.company_b.favicon = BinaryBytes(b'company-b-icon', filename='b.ico')
        self.authenticate('ee_theme_user', 'ee_theme_user')
        favicon_url = f'/web/image/res.company/{self.company_b.id}/favicon'
        self.assertIn(favicon_url, self.url_open('/odoo').text)
        self.assertEqual(self.url_open(favicon_url).content, b'company-b-icon')
