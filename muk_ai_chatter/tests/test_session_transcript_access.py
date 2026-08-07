from __future__ import annotations

from odoo import models
from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install', 'muk_ai_chatter')
class TestSessionTranscriptAccess(TransactionCase):
    """Test that a chat and its files stay with the user who held it."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        """Set up an owned session with a transcript linked to a shared record."""
        super().setUpClass()
        cls.owner = new_test_user(
            cls.env,
            login='transcript_owner',
            groups='base.group_user',
        )
        cls.reader = new_test_user(
            cls.env,
            login='transcript_reader',
            groups='base.group_user',
        )
        cls.record = cls.env['res.partner'].create({'name': 'Linked Record'})
        cls.transcript = [{'role': 'assistant', 'content': 'secret tool output'}]
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
        cls.session.sudo().write({'conversation': cls.transcript})
        cls.session.sudo()._append_event(
            {'kind': 'text', 'content': 'secret tool output'}
        )
        cls.session.sudo().write({'last_text': 'secret tool output'})
        cls.session.sudo().write(
            {
                'compose_interface': 'mail_composer',
                'compose_draft': 'the unsent offer is 40% off',
                'compose_selection': '40% off',
            }
        )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @classmethod
    def _attach(cls, name: str) -> models.BaseModel:
        """Attach a file to the session the way a chat upload would."""
        return (
            cls.env['ir.attachment']
            .sudo()
            .create(
                {
                    'name': name,
                    'raw': b'the secret rate is 999',
                    'res_model': 'muk_ai.session',
                    'res_id': cls.session.id,
                }
            )
        )

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_reader_cannot_read_a_foreign_session(self):
        with self.assertRaises(AccessError):
            self.session.with_user(self.reader).read(['name', 'conversation'])

    def test_reader_cannot_search_a_foreign_session(self):
        found = (
            self.env['muk_ai.session']
            .with_user(self.reader)
            .search([('id', '=', self.session.id)])
        )
        self.assertFalse(found)

    def test_reader_cannot_search_for_words_in_the_transcript(self):
        found = (
            self.env['muk_ai.session']
            .with_user(self.reader)
            .search([('conversation', 'ilike', 'secret tool output')])
        )
        self.assertFalse(found)

    def test_reader_cannot_search_for_words_in_the_draft(self):
        found = (
            self.env['muk_ai.session']
            .with_user(self.reader)
            .search([('compose_draft', 'ilike', 'unsent offer')])
        )
        self.assertFalse(found)

    def test_reader_cannot_read_a_file_from_the_chat(self):
        attachment = self._attach('exported-rates.txt')
        with self.assertRaises(AccessError):
            attachment.with_user(self.reader).read(['datas'])

    def test_reader_cannot_find_a_file_from_the_chat(self):
        self._attach('exported-rates.txt')
        found = (
            self.env['ir.attachment']
            .with_user(self.reader)
            .search(
                [('res_model', '=', 'muk_ai.session'), ('res_id', '=', self.session.id)]
            )
        )
        self.assertFalse(found)

    def test_owner_keeps_the_whole_transcript(self):
        session = self.session.with_user(self.owner)
        self.assertEqual(
            session.read(['conversation'])[0]['conversation'], self.transcript
        )
        self.assertEqual(session.last_text, 'secret tool output')
        self.assertEqual(session.compose_draft, 'the unsent offer is 40% off')

    def test_owner_still_sees_events(self):
        events = self.session.with_user(self.owner).fetch_events()
        self.assertTrue(events['events'])

    def test_owner_still_reads_the_files_of_their_own_chat(self):
        attachment = self._attach('mine.txt')
        self.assertTrue(attachment.with_user(self.owner).read(['datas']))

    def test_admin_keeps_the_whole_transcript(self):
        session = self.session.with_user(self.env.ref('base.user_admin'))
        self.assertEqual(
            session.read(['conversation'])[0]['conversation'], self.transcript
        )
