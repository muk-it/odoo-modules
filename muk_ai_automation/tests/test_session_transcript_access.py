from __future__ import annotations

from odoo.tests.common import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestSessionTranscriptAccess(TransactionCase):
    """Test that granted non-owner readers never see the session transcript."""

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

    def test_reader_can_read_metadata(self):
        session = self.session.with_user(self.reader)
        self.assertTrue(session.with_user(self.reader).has_access('read'))
        self.assertEqual(session.read(['name'])[0]['name'], 'Linked Session')

    def test_reader_read_blanks_conversation(self):
        session = self.session.with_user(self.reader)
        row = session.read(['name', 'conversation'])[0]
        self.assertEqual(row['name'], 'Linked Session')
        self.assertEqual(row['conversation'], [])

    def test_reader_snapshot_hides_conversation(self):
        session = self.session.with_user(self.reader)
        snapshot = session.get_snapshot(include_conversation=True)
        self.assertEqual(snapshot.get('conversation'), [])

    def test_reader_fetch_events_is_empty(self):
        session = self.session.with_user(self.reader)
        self.assertEqual(session.fetch_events()['events'], [])

    def test_reader_display_events_blanked(self):
        session = self.session.with_user(self.reader)
        self.assertEqual(session.read(['display_events'])[0]['display_events'], [])

    def test_reader_snapshot_hides_events_and_last_text(self):
        session = self.session.with_user(self.reader)
        snapshot = session.get_snapshot(include_conversation=True)
        self.assertEqual(snapshot['events'], [])
        self.assertFalse(snapshot['last_text'])

    def test_reader_read_blanks_last_text(self):
        session = self.session.with_user(self.reader)
        self.assertFalse(session.read(['last_text'])[0]['last_text'])

    def test_reader_search_read_blanks_transcript(self):
        model = self.env['muk_ai.session'].with_user(self.reader)
        rows = model.search_read(
            [('id', '=', self.session.id)], ['name', 'conversation', 'last_text']
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['name'], 'Linked Session')
        self.assertEqual(rows[0]['conversation'], [])
        self.assertFalse(rows[0]['last_text'])

    def test_reader_export_blanks_transcript(self):
        self.reader.sudo().group_ids |= self.env.ref('base.group_allow_export')
        session = self.session.with_user(self.reader)
        datas = session.export_data(['name', 'conversation', 'last_text'])['datas']
        self.assertEqual(len(datas), 1)
        self.assertEqual(datas[0][0], 'Linked Session')
        self.assertNotIn('secret tool output', str(datas[0][1]))
        self.assertNotIn('secret tool output', str(datas[0][2]))

    def test_owner_search_read_keeps_transcript(self):
        model = self.env['muk_ai.session'].with_user(self.owner)
        rows = model.search_read(
            [('id', '=', self.session.id)], ['conversation', 'last_text']
        )
        self.assertEqual(rows[0]['conversation'], self.transcript)
        self.assertEqual(rows[0]['last_text'], 'secret tool output')

    def test_owner_export_keeps_transcript(self):
        self.owner.sudo().group_ids |= self.env.ref('base.group_allow_export')
        session = self.session.with_user(self.owner)
        datas = session.export_data(['conversation', 'last_text'])['datas']
        self.assertIn('secret tool output', str(datas[0][0]))
        self.assertEqual(datas[0][1], 'secret tool output')

    def test_owner_keeps_conversation(self):
        session = self.session.with_user(self.owner)
        self.assertEqual(
            session.read(['conversation'])[0]['conversation'], self.transcript
        )
        snapshot = session.get_snapshot(include_conversation=True)
        self.assertEqual(snapshot['conversation'], self.transcript)

    def test_owner_still_sees_events(self):
        session = self.session.with_user(self.owner)
        self.assertTrue(session.fetch_events()['events'])
        snapshot = session.get_snapshot(include_conversation=True)
        self.assertEqual(snapshot['last_text'], 'secret tool output')

    def test_admin_keeps_conversation(self):
        row = self.session.read(['conversation'])[0]
        self.assertEqual(row['conversation'], self.transcript)
