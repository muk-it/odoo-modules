from __future__ import annotations

from odoo import models
from odoo.exceptions import AccessError, UserError
from odoo.tests.common import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestAiSecurity(TransactionCase):
    """Verify access rights and record-level security on AI models."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.user_a = new_test_user(
            cls.env,
            login='ai_user_a',
            groups='base.group_user',
        )
        cls.user_b = new_test_user(
            cls.env,
            login='ai_user_b',
            groups='base.group_user',
        )
        cls.manager = new_test_user(
            cls.env,
            login='ai_manager',
            groups='base.group_system',
        )

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_user_sees_own_sessions_only(self):
        session_a = (
            self.env['muk_ai.session']
            .with_user(self.user_a)
            .create({'name': 'A session'})
        )
        self.env['muk_ai.session'].with_user(self.user_b).create({'name': 'B session'})
        visible_to_a = (
            self.env['muk_ai.session']
            .with_user(self.user_a)
            .search([('name', 'in', ('A session', 'B session'))])
        )
        self.assertEqual(visible_to_a, session_a)

    def test_manager_sees_all_sessions(self):
        self.env['muk_ai.session'].with_user(self.user_a).create({'name': 'A session'})
        self.env['muk_ai.session'].with_user(self.user_b).create({'name': 'B session'})
        visible = (
            self.env['muk_ai.session']
            .with_user(self.manager)
            .search([('name', 'in', ('A session', 'B session'))])
        )
        self.assertEqual(len(visible), 2)

    def test_agent_write_requires_manager(self):
        agent = self.env['muk_ai.agent'].create({'name': 'Read only'})
        with self.assertRaises(AccessError):
            agent.with_user(self.user_a).write({'name': 'Hacked'})
        agent.with_user(self.manager).write({'name': 'Updated'})
        self.assertEqual(agent.name, 'Updated')

    def test_rate_limit_blocks_excessive_creates(self):
        provider = self.env.ref('muk_ai.provider_openai').sudo()
        provider.write({'rate_limit': 2})
        self.env.company.default_ai_provider_id = provider
        Session = self.env['muk_ai.session'].with_user(self.user_a)
        Session.create({'name': 's1'})
        Session.create({'name': 's2'})
        with self.assertRaises(UserError):
            Session.create({'name': 's3'})

    # ----------------------------------------------------------
    # Tests: cross-user method access
    # ----------------------------------------------------------

    def _owned_session(self) -> models.Model:
        """Create a session owned by ``user_a``."""
        return (
            self.env['muk_ai.session'].with_user(self.user_a).create({'name': 'Owned'})
        )

    def _seed_events(self, session: models.Model, kinds: list[str]) -> None:
        """Append one replay event per given kind to the session log."""
        events = self.env['muk_ai.session.event'].sudo()
        for sequence, kind in enumerate(kinds):
            events.create(
                {
                    'session_id': session.id,
                    'sequence': sequence,
                    'kind': kind,
                    'payload': {'kind': kind, 'content': f'{kind}-{sequence}'},
                }
            )

    def test_fetch_events_allowed_for_owner(self):
        session = self._owned_session()
        self._seed_events(session, ['user_message', 'text'])
        result = session.with_user(self.user_a).fetch_events()
        self.assertEqual(
            [event['kind'] for event in result['events']],
            ['user_message', 'text'],
        )
        self.assertEqual(result['events'][0]['content'], 'user_message-0')
        self.assertFalse(result['has_more_older'])
        self.assertEqual(result['oldest_sequence'], 0)

    def test_fetch_events_denied_cross_user(self):
        session = self._owned_session()
        self._seed_events(session, ['user_message'])
        with self.assertRaises(AccessError):
            session.with_user(self.user_b).fetch_events()

    def test_get_snapshot_denied_cross_user(self):
        session = self._owned_session()
        with self.assertRaises(AccessError):
            session.with_user(self.user_b).get_snapshot()

    def test_discard_attachments_denied_cross_user(self):
        session = self._owned_session()
        with self.assertRaises(AccessError):
            session.with_user(self.user_b).discard_attachments([1])

    def test_action_open_denied_cross_user(self):
        session = self._owned_session()
        with self.assertRaises(AccessError):
            session.with_user(self.user_b).action_open()

    def test_action_stop_denied_cross_user(self):
        session = self._owned_session()
        with self.assertRaises(AccessError):
            session.with_user(self.user_b).action_stop()
