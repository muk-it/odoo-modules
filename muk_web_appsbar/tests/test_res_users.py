from __future__ import annotations

from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, new_test_user, tagged
from odoo.tools import mute_logger


@tagged('post_install', '-at_install')
class TestResUsers(TransactionCase):
    """Cover the self-service access granted to the sidebar preference."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.user = new_test_user(
            cls.env,
            login='appsbar_pref',
            password='appsbar_pref',
            groups='base.group_user',
        )
        cls.other = new_test_user(
            cls.env,
            login='appsbar_other',
            password='appsbar_other',
            groups='base.group_user',
        )

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_default_sidebar_type(self):
        self.assertEqual(self.user.sidebar_type, 'large')

    def test_user_updates_own_sidebar_type(self):
        self.user.with_user(self.user).write({'sidebar_type': 'small'})
        self.assertEqual(self.user.sidebar_type, 'small')
        self.assertEqual(
            self.user.with_user(self.user).read(['sidebar_type'])[0]['sidebar_type'],
            'small',
        )

    @mute_logger('odoo.models')
    def test_user_cannot_update_unlisted_field(self):
        with self.assertRaises(AccessError):
            self.user.with_user(self.user).write({'login': 'appsbar_hijack'})

    @mute_logger('odoo.models')
    def test_user_cannot_update_other_user_sidebar_type(self):
        with self.assertRaises(AccessError):
            self.other.with_user(self.user).write({'sidebar_type': 'invisible'})
