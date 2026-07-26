from __future__ import annotations

from odoo import models
from odoo.exceptions import AccessError
from odoo.tests.common import new_test_user

from odoo.addons.muk_ai_browser.tests.common import BrowserTestCommon


class TestRecordRules(BrowserTestCommon):
    """Verify browser records are scoped to their owning user by record rules."""

    def _user(self, login: str) -> models.BaseModel:
        """Create a plain internal user."""
        return new_test_user(self.env, login=login, groups='base.group_user')

    def _owned_browser_session(self, user: models.BaseModel) -> models.BaseModel:
        """Attach a browser session to a chat session owned by ``user``."""
        ai_session = self.env['muk_ai.session'].with_user(user).create({'name': 'sec'})
        return self._browser_session(ai_session=ai_session)

    def test_permission_grant_is_owner_scoped(self):
        user_a = self._user('rr_perm_a')
        user_b = self._user('rr_perm_b')
        permission = self.env['muk_ai_browser.permission']
        with self.assertRaises(AccessError):
            permission.with_user(user_b).create(
                {
                    'user_id': user_a.id,
                    'origin': 'https://evil.example',
                    'mode': 'follow_plan',
                }
            )
        a_grant = permission.with_user(user_a).create(
            {
                'user_id': user_a.id,
                'origin': 'https://good.example',
                'mode': 'follow_plan',
            }
        )
        self.assertFalse(permission.with_user(user_b).search([('id', '=', a_grant.id)]))

    def test_event_not_readable_by_other_user(self):
        user_a = self._user('rr_evt_a')
        user_b = self._user('rr_evt_b')
        browser_session = self._owned_browser_session(user_a)
        event = browser_session._enqueue_event('event', {'secret': 'x'})
        events = self.env['muk_ai_browser.event']
        self.assertFalse(events.with_user(user_b).search([('id', '=', event.id)]))
        self.assertTrue(events.with_user(user_a).search([('id', '=', event.id)]))

    def test_session_is_owner_scoped(self):
        user_a = self._user('rr_ses_a')
        user_b = self._user('rr_ses_b')
        browser_session = self._owned_browser_session(user_a)
        sessions = self.env['muk_ai_browser.session']
        self.assertFalse(
            sessions.with_user(user_b).search([('id', '=', browser_session.id)])
        )
        with self.assertRaises(AccessError):
            browser_session.with_user(user_b).write(
                {'last_origin': 'https://granted.example'}
            )
