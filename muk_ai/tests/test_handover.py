from __future__ import annotations

from unittest.mock import patch

from odoo import models
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user


@tagged('post_install', '-at_install', 'muk_ai')
class TestHandover(TransactionCase):
    """Verify ownership transfer of an AI session via action_handover."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.user_a = new_test_user(cls.env, login='ho_a', groups='base.group_user')
        cls.user_b = new_test_user(cls.env, login='ho_b', groups='base.group_user')
        cls.manager = new_test_user(cls.env, login='ho_mgr', groups='base.group_system')
        cls.portal = new_test_user(
            cls.env, login='ho_portal', groups='base.group_portal'
        )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _owned_session(self, user: models.Model) -> models.Model:
        """Return a fresh session owned by the given user."""
        return self.env['muk_ai.session'].with_user(user).create({'name': 'handover'})

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_handover_reassigns_owner(self):
        session = self._owned_session(self.user_a)
        session.with_user(self.user_a).action_handover(self.user_b.id)
        self.assertEqual(session.sudo().user_id, self.user_b)

    def test_old_owner_loses_access(self):
        session = self._owned_session(self.user_a)
        session.with_user(self.user_a).action_handover(self.user_b.id)
        visible = (
            self.env['muk_ai.session']
            .with_user(self.user_a)
            .search([('id', '=', session.id)])
        )
        self.assertFalse(visible)

    def test_new_owner_gains_access(self):
        session = self._owned_session(self.user_a)
        session.with_user(self.user_a).action_handover(self.user_b.id)
        visible = (
            self.env['muk_ai.session']
            .with_user(self.user_b)
            .search([('id', '=', session.id)])
        )
        self.assertEqual(visible, session.sudo())

    def test_handover_pushes_badges_to_both(self):
        session = self._owned_session(self.user_a)
        captured = []

        def fake(self_arg, target, notification_type, message):
            captured.append((target, notification_type, message))

        with patch.object(
            type(self.env['bus.bus']),
            '_sendone',
            autospec=True,
            side_effect=fake,
        ):
            session.with_user(self.user_a).action_handover(self.user_b.id)
        badges = {
            target.id: message
            for target, notification_type, message in captured
            if notification_type == 'muk_ai.notification_badge'
        }
        self.assertEqual(
            set(badges),
            {self.user_a.partner_id.id, self.user_b.partner_id.id},
        )
        self.assertEqual(
            badges[self.user_b.partner_id.id],
            {'count': 1, 'session_ids': [session.id], 'space_unread': {}},
        )
        self.assertEqual(
            badges[self.user_a.partner_id.id],
            {'count': 0, 'session_ids': [], 'space_unread': {}},
        )

    def test_manager_can_hand_over_any_session(self):
        session = self._owned_session(self.user_a)
        session.with_user(self.manager).action_handover(self.user_b.id)
        self.assertEqual(session.sudo().user_id, self.user_b)

    def test_non_owner_cannot_hand_over(self):
        session = self._owned_session(self.user_a)
        with self.assertRaises(AccessError):
            session.with_user(self.user_b).action_handover(self.manager.id)

    def test_portal_target_rejected(self):
        session = self._owned_session(self.user_a)
        with self.assertRaises(UserError):
            session.with_user(self.user_a).action_handover(self.portal.id)

    def test_inactive_target_rejected(self):
        session = self._owned_session(self.user_a)
        self.user_b.sudo().active = False
        with self.assertRaises(UserError):
            session.with_user(self.user_a).action_handover(self.user_b.id)

    def test_running_session_cannot_be_handed_over(self):
        session = self._owned_session(self.user_a)
        session.sudo().state = 'running'
        with self.assertRaises(UserError):
            session.with_user(self.user_a).action_handover(self.user_b.id)
