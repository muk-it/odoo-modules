from __future__ import annotations

from unittest.mock import patch

from odoo.exceptions import AccessError
from odoo.tests import new_test_user

from odoo.addons.muk_ai_chatter.tests.common import ChatterTestCommon


class TestSessionAccess(ChatterTestCommon):
    """Test that linking a session to a record grants nobody anything."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        """Set up a session owner, a reader and a session linked to a shared record."""
        super().setUpClass()
        cls.owner = new_test_user(cls.env, login='access_owner')
        cls.reader = new_test_user(cls.env, login='access_reader')
        cls.session = (
            cls.env['muk_ai.session']
            .with_user(cls.owner)
            .create(
                {
                    'name': 'Linked Session',
                    'res_model': 'res.partner',
                    'res_id': cls.record.id,
                }
            )
        )
        cls.session.sudo().write(
            {
                'conversation': [{'role': 'assistant', 'content': 'secret output'}],
                'compose_draft': 'the unsent offer is 40% off',
            }
        )

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_a_reader_of_the_record_finds_no_session_on_it(self):
        manager = new_test_user(
            self.env, login='access_manager', groups='base.group_erp_manager'
        )
        Session = self.env['muk_ai.session']
        for user in (self.reader, manager):
            for domain in (
                [('id', '=', self.session.id)],
                [('conversation', 'ilike', 'secret output')],
                [('compose_draft', 'ilike', 'unsent offer')],
            ):
                with self.subTest(user=user.login, domain=domain):
                    self.assertFalse(Session.with_user(user).search(domain))
            with self.assertRaises(AccessError):
                self.session.with_user(user).read(['name'])

    def test_the_chatter_lists_only_the_callers_sessions(self):
        admin = self.env.ref('base.user_admin')
        for user, expected in (
            (self.reader, []),
            (self.owner, [self.session.id]),
            (admin, [self.session.id]),
        ):
            with self.subTest(user=user.login):
                summary = self.record.with_user(user).get_ai_sessions_summary()
                entry = summary[self.record.id]
                self.assertEqual([row['id'] for row in entry['entries']], expected)
                self.assertEqual(entry['total'], len(expected))

    def test_a_linked_session_is_announced_on_its_record_and_reads_it(self):
        body = self._messages_on(self.record)[-1].body
        self.assertIn('started for this record', body)
        self.assertIn('/odoo/ai-sessions/%d' % self.session.id, body)
        session = self.session.sudo()
        self.assertIn('Mentioned Record', str(session._build_request_inputs()))
        self.record.unlink()
        self.assertIsNone(session._linked_record())

    def test_a_record_the_owner_cannot_read_is_neither_announced_nor_used(self):
        hidden = self.env['res.partner'].create({'name': 'Hidden Target'})
        self._hide(hidden)
        before = len(self._messages_on(hidden))
        session = (
            self.env['muk_ai.session']
            .with_user(self.owner)
            .create({'name': 'Probe', 'res_model': 'res.partner', 'res_id': hidden.id})
        )
        self.assertEqual(len(self._messages_on(hidden)), before)
        self.assertIsNone(session._linked_record())
        rendered = str(session.sudo()._build_request_inputs())
        self.assertNotIn('Hidden Target', rendered)

    def test_a_record_refusing_the_note_still_gets_its_session(self):
        partner = self.env['res.partner'].create({'name': 'Unpostable Target'})
        before = self._messages_on(partner)
        with patch.object(
            type(partner), 'message_post', autospec=True, side_effect=RuntimeError
        ):
            session = self.env['muk_ai.session'].create(
                {'name': 'Resilient', 'res_model': 'res.partner', 'res_id': partner.id}
            )
        self.assertTrue(session.exists())
        self.assertEqual(self._messages_on(partner), before)
