from __future__ import annotations

import base64

from odoo.tests import tagged
from odoo.tests.common import HttpCase, new_test_user


@tagged('post_install', '-at_install')
class TestSessionInfo(HttpCase):
    """Cover the background image flags added to the session info companies."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.company_a = cls.env.company
        cls.company_b = cls.env['res.company'].create({'name': 'Theme Co B'})
        cls.user = new_test_user(
            cls.env,
            login='ee_theme_session',
            password='ee_theme_session',
            groups='base.group_user',
            company_id=cls.company_a.id,
            company_ids=[(6, 0, [cls.company_a.id, cls.company_b.id])],
        )
        cls.env['res.users.settings']._find_or_create_for_user(cls.user)

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _get_allowed_companies(self) -> dict:
        """Return the allowed companies of a fresh session, keyed by company id."""
        self.authenticate('ee_theme_session', 'ee_theme_session')
        info = self.make_jsonrpc_request(
            '/web/session/get_session_info', {}, timeout=120
        )
        allowed = info['user_companies']['allowed_companies']
        return {int(key): value for key, value in allowed.items()}

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_flags_reflect_the_company_images(self):
        self.company_a.background_image_light = base64.b64encode(b'light')
        self.company_a.background_image_dark = False
        self.company_b.background_image_light = False
        self.company_b.background_image_dark = base64.b64encode(b'dark')
        allowed = self._get_allowed_companies()
        self.assertTrue(allowed[self.company_a.id]['has_background_image_light'])
        self.assertFalse(allowed[self.company_a.id]['has_background_image_dark'])
        self.assertFalse(allowed[self.company_b.id]['has_background_image_light'])
        self.assertTrue(allowed[self.company_b.id]['has_background_image_dark'])

    def test_archived_company_does_not_break_session_info(self):
        self.company_b.active = False
        allowed = self._get_allowed_companies()
        self.assertNotIn(self.company_b.id, allowed)
        self.assertIn('has_background_image_light', allowed[self.company_a.id])
        self.assertIn('has_background_image_dark', allowed[self.company_a.id])
