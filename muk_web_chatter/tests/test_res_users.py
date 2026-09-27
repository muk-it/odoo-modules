from __future__ import annotations

from odoo.tests import Form, HttpCase, new_test_user


class TestResUsers(HttpCase):
    """Cover the chatter position a user picks in the preferences."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        """Create the internal user who edits the preference."""
        super().setUpClass()
        cls.user = new_test_user(
            cls.env,
            login='chatter_user',
            password='chatter_user',
            groups='base.group_user',
        )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _get_chatter_position(self) -> str:
        """Return the chatter position of a freshly opened user session."""
        self.authenticate('chatter_user', 'chatter_user')
        info = self.make_jsonrpc_request(
            '/web/session/get_session_info', {}, timeout=120
        )
        return info['chatter_position']

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_user_sets_the_chatter_position_in_the_preferences(self):
        self.assertEqual(self._get_chatter_position(), 'side')
        with Form(
            self.user.with_user(self.user), view='base.view_users_form_simple_modif'
        ) as preferences:
            preferences.chatter_position = 'bottom'
        self.assertEqual(self._get_chatter_position(), 'bottom')
