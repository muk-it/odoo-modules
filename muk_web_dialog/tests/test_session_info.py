from odoo.tests import Form, HttpCase, new_test_user


class TestSessionInfo(HttpCase):
    """Cover the dialog size preference from the preferences form to the session."""

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_user_preference_reaches_session_info(self):
        user = new_test_user(self.env, login='dialog_user', groups='base.group_user')
        self.authenticate('dialog_user', 'dialog_user')
        info = self.make_jsonrpc_request('/web/session/get_session_info', {})
        self.assertEqual(info['dialog_size'], 'minimize')
        with Form(
            user.with_user(user), view='base.view_users_form_simple_modif'
        ) as form:
            form.dialog_size = 'maximize'
        info = self.make_jsonrpc_request('/web/session/get_session_info', {})
        self.assertEqual(info['dialog_size'], 'maximize')
