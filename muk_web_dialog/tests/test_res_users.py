from __future__ import annotations

from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, new_test_user, tagged
from odoo.tools import mute_logger


@tagged('post_install', '-at_install')
class TestResUsers(TransactionCase):
    """Cover the self-service access granted to the dialog size preference."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.user = new_test_user(
            cls.env,
            login='dialog_pref',
            password='dialog_pref',
            groups='base.group_user',
        )
        cls.other = new_test_user(
            cls.env,
            login='dialog_other',
            password='dialog_other',
            groups='base.group_user',
        )

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_default_dialog_size(self):
        self.assertEqual(self.user.dialog_size, 'minimize')

    def test_user_updates_own_dialog_size(self):
        self.user.with_user(self.user).write({'dialog_size': 'maximize'})
        self.assertEqual(self.user.dialog_size, 'maximize')
        self.assertEqual(
            self.user.with_user(self.user).read(['dialog_size'])[0]['dialog_size'],
            'maximize',
        )

    @mute_logger('odoo.models')
    def test_user_cannot_update_unlisted_field(self):
        with self.assertRaises(AccessError):
            self.user.with_user(self.user).write({'login': 'dialog_hijack'})

    @mute_logger('odoo.models')
    def test_user_cannot_update_other_user_dialog_size(self):
        with self.assertRaises(AccessError):
            self.other.with_user(self.user).write({'dialog_size': 'maximize'})
