from __future__ import annotations

from odoo.tests import HttpCase, new_test_user


class TestSessionInfo(HttpCase):
    """Cover the quick-create flag exposed through the session info."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        """Create the user the tests run as."""
        super().setUpClass()
        new_test_user(
            cls.env,
            login='utils_session',
            password='utils_session',
            groups='base.group_user',
        )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _get_session_info(self) -> dict:
        """Return the session info payload for a freshly authenticated user."""
        self.authenticate('utils_session', 'utils_session')
        return self.make_jsonrpc_request(
            '/web/session/get_session_info', {}, timeout=120
        )

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_session_info_quick_create_default(self):
        self.assertFalse(self._get_session_info()['disable_quick_create'])

    def test_session_info_quick_create_from_settings(self):
        self.env['res.config.settings'].create(
            {'disable_many2one_quick_create': True}
        ).execute()
        self.assertTrue(self._get_session_info()['disable_quick_create'])
