from __future__ import annotations

from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, new_test_user, tagged
from odoo.tools import mute_logger


@tagged('post_install', '-at_install')
class TestResUsers(TransactionCase):
    """Cover the self-service access granted to the chatter position."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.user = new_test_user(
            cls.env,
            login='chatter_pref',
            password='chatter_pref',
            groups='base.group_user',
        )
        cls.other = new_test_user(
            cls.env,
            login='chatter_other',
            password='chatter_other',
            groups='base.group_user',
        )

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_default_chatter_position(self):
        self.assertEqual(self.user.chatter_position, 'side')

    def test_user_updates_own_chatter_position(self):
        self.user.with_user(self.user).write({'chatter_position': 'bottom'})
        self.assertEqual(self.user.chatter_position, 'bottom')
        self.assertEqual(
            self.user.with_user(self.user).read(['chatter_position'])[0][
                'chatter_position'
            ],
            'bottom',
        )

    @mute_logger('odoo.models')
    def test_user_cannot_update_unlisted_field(self):
        with self.assertRaises(AccessError):
            self.user.with_user(self.user).write({'login': 'chatter_hijack'})

    @mute_logger('odoo.models')
    def test_user_cannot_update_other_user_chatter_position(self):
        with self.assertRaises(AccessError):
            self.other.with_user(self.user).write({'chatter_position': 'bottom'})
