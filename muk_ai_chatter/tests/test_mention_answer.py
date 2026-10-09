from __future__ import annotations

from odoo.addons.muk_ai_chatter.tests.common import ChatterTestCommon


class TestMentionAnswer(ChatterTestCommon):
    """Test that the placeholder note becomes the answer, whatever happens."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    def setUp(self) -> None:
        """Start a mention in a conversation and keep the session it spawned."""
        super().setUp()
        with self._mute_worker():
            self._mention()
        self.session = self._sessions_on(self.channel)

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _end(self, state: str = 'done', **values: object) -> str:
        """End the run in ``state`` and return the body of the answer note."""
        self.session.write({'state': state, **values})
        self.session._notify_state_transition({'state': state})
        return str(self.session.answer_message_id.body)

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_the_agent_answers_in_place_of_its_placeholder(self):
        answer = self.session.answer_message_id
        self.assertIn('Working on it', answer.body)
        self.assertEqual(answer.author_id, self.agent.partner_id)
        self.assertFalse(self.agent.partner_id.active)
        self.assertEqual(answer.parent_id, self.session.mention_message_id)
        self.assertEqual(answer.subtype_id, self.env.ref('mail.mt_comment'))
        body = self._end(last_text='Here is the summary.')
        self.assertEqual(self.session.answer_message_id, answer)
        self.assertIn('Here is the summary.', body)
        self.assertNotIn('Working on it', body)
        self.assertIn('/odoo/ai-sessions/%d' % self.session.id, body)
        self.assertNotIn(
            self.agent.partner_id, self.channel.channel_member_ids.partner_id
        )
        self.assertNotIn(
            self.agent.partner_id, self.channel.message_follower_ids.partner_id
        )
        bodies = self._messages_on(self.channel).mapped('body')
        self.assertFalse([b for b in bodies if 'started for this record' in str(b)])

    def test_every_ending_closes_the_note(self):
        for state, values, expected in (
            ('error', {'error_message': 'key sk-123 refused'}, 'could not answer'),
            ('done', {'last_text': False}, 'nothing to add'),
            ('stopped', {'last_text': 'Partial answer'}, 'Partial answer'),
            ('done', {'last_text': '<script>alert(1)</script>'}, '&lt;script&gt;'),
        ):
            with self.subTest(state=state, expected=expected):
                body = self._end(state, **values)
                self.assertIn(expected, body)
                self.assertNotIn('Working on it', body)
                self.assertNotIn('<script>', body)
                self.assertNotIn('sk-123', body)

    def test_a_record_the_answer_names_becomes_a_link(self):
        body = self._end(
            last_text='See res.partner,%d and no.such.model/12.' % self.record.id
        )
        self.assertIn('href="/odoo/res.partner/%d"' % self.record.id, body)
        self.assertIn('data-oe-model="res.partner"', body)
        self.assertNotIn('/odoo/no.such.model', body)

    def test_a_run_still_going_does_not_close_the_note(self):
        self.session.write({'state': 'done', 'last_text': 'Partial.'})
        self.session.with_context(
            muk_ai_skip_done_notification=True
        )._notify_state_transition({'state': 'done'})
        self.env['muk_ai.session.pending'].create(
            {'session_id': self.session.id, 'content': 'and one more thing'}
        )
        self.session._notify_state_transition({'state': 'done'})
        self.assertIn('Working on it', self.session.answer_message_id.body)

    def test_a_lost_placeholder_is_posted_at_the_end_instead(self):
        self.session.answer_message_id.unlink()
        self.assertIn('Recovered answer.', self._end(last_text='Recovered answer.'))

    def test_a_mention_can_neither_ask_nor_wait_while_a_chat_can(self):
        addenda = '\n'.join(self.session._system_prompt_addenda())
        self.assertIn('never call ask_user', addenda)
        self.assertEqual(self.session._effective_approval_mode(), 'off')
        self.assertFalse(self.session._available_client_kinds())
        self.assertFalse(self.session._can_ask_user())
        plain = self.env['muk_ai.session'].create({'name': 'Plain'})
        self.assertIn('webclient', plain._available_client_kinds())
        self.assertTrue(plain._can_ask_user())

    def test_a_linked_session_that_is_no_mention_keeps_its_answer_to_itself(self):
        session = self.env['muk_ai.session'].create(
            {
                'name': 'Automation Run',
                'res_model': 'res.partner',
                'res_id': self.record.id,
            }
        )
        before = self._messages_on(self.record)
        session.write({'state': 'done', 'last_text': 'internal-only transcript'})
        session._notify_state_transition({'state': 'done'})
        self.assertEqual(self._messages_on(self.record), before)
        self.assertFalse(session.answer_message_id)
