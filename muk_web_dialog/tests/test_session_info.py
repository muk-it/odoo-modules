from __future__ import annotations

from odoo.tests import tagged
from odoo.tests.common import HttpCase, new_test_user


@tagged('post_install', '-at_install')
class TestSessionInfo(HttpCase):
    """Cover the dialog size preference exposed through the session info."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.user = new_test_user(
            cls.env,
            login='dialog_session',
            password='dialog_session',
            groups='base.group_user',
        )
        cls.portal_user = new_test_user(
            cls.env,
            login='dialog_portal',
            password='dialog_portal',
            groups='base.group_portal',
        )
        settings = cls.env['res.users.settings']
        settings._find_or_create_for_user(cls.user)
        settings._find_or_create_for_user(cls.portal_user)

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _get_session_info(self, login: str) -> dict:
        """Return the session info payload for a freshly authenticated login."""
        self.authenticate(login, login)
        return self.make_jsonrpc_request(
            '/web/session/get_session_info', {}, timeout=120
        )

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_session_info_exposes_dialog_size(self):
        info = self._get_session_info('dialog_session')
        self.assertEqual(info['dialog_size'], 'minimize')
        self.user.dialog_size = 'maximize'
        info = self._get_session_info('dialog_session')
        self.assertEqual(info['dialog_size'], 'maximize')

    def test_portal_user_session_info_exposes_dialog_size(self):
        info = self._get_session_info('dialog_portal')
        self.assertEqual(info['dialog_size'], 'minimize')
