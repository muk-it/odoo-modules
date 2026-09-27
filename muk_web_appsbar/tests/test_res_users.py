from odoo.tests import TransactionCase, new_test_user


class TestResUsers(TransactionCase):
    """Cover the self-service access granted to the sidebar preference."""

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_user_updates_own_sidebar_type(self):
        user = new_test_user(self.env, login='appsbar_pref', groups='base.group_user')
        user.with_user(user).write({'sidebar_type': 'small'})
        self.assertEqual(user.sidebar_type, 'small')
