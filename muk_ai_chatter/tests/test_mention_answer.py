from __future__ import annotations

from odoo.tests.common import tagged

from .common import ChatterTestCommon


@tagged('post_install', '-at_install', 'muk_ai_chatter')
class TestMentionAnswer(ChatterTestCommon):
    """Test that the placeholder note becomes the answer, whatever happens."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    def setUp(self) -> None:
        """Start a mention in a conversation and keep the session it spawned."""
        super().setUp()
        with self._mute_worker():
            self._mention(record=self.channel)
        self.session = self._sessions_on(self.channel)

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_the_placeholder_says_the_agent_picked_it_up(self):
        self.assertIn('Working on it', self.session.answer_message_id.body)

    def test_the_answer_replaces_the_placeholder_in_place(self):
        message = self.session.answer_message_id
        self.session.write({'state': 'done', 'last_text': 'Here is the summary.'})
        self.session._notify_state_transition({'state': 'done'})
        self.assertEqual(self.session.answer_message_id, message)
        self.assertIn('Here is the summary.', message.body)
        self.assertNotIn('Working on it', message.body)

    def test_a_failed_run_says_so_instead_of_staying_silent(self):
        self.session.write({'state': 'error', 'error_message': 'provider exploded'})
        self.session._notify_state_transition({'state': 'error'})
        body = self.session.answer_message_id.body
        self.assertIn('could not answer', body)
        self.assertIn('provider exploded', body)

    def test_an_answer_with_nothing_in_it_still_closes_the_note(self):
        self.session.write({'state': 'done', 'last_text': False})
        self.session._notify_state_transition({'state': 'done'})
        body = self.session.answer_message_id.body
        self.assertIn('nothing to add', body)
        self.assertNotIn('Working on it', body)

    def test_the_answer_is_escaped_not_injected(self):
        self.session.write({'state': 'done', 'last_text': '<script>alert(1)</script>'})
        self.session._notify_state_transition({'state': 'done'})
        body = self.session.answer_message_id.body
        self.assertNotIn('<script>', body)
        self.assertIn('&lt;script&gt;', body)

    def test_a_record_the_answer_names_becomes_a_link(self):
        self.session.write(
            {
                'state': 'done',
                'last_text': 'See res.partner,%d and res.partner/%d.'
                % (self.record.id, self.record.id),
            }
        )
        self.session._notify_state_transition({'state': 'done'})
        body = self.session.answer_message_id.body
        self.assertEqual(body.count('/odoo/res.partner/%d' % self.record.id), 2)
        self.assertIn('data-oe-model="res.partner"', body)

    def test_something_that_only_looks_like_a_record_is_left_alone(self):
        self.session.write(
            {'state': 'done', 'last_text': 'Version no.such.model/12 shipped.'}
        )
        self.session._notify_state_transition({'state': 'done'})
        body = self.session.answer_message_id.body
        self.assertNotIn('<a href="/odoo/no.such.model', body)
        self.assertIn('no.such.model/12', body)

    def test_the_answer_links_back_to_the_run(self):
        self.session.write({'state': 'done', 'last_text': 'Done.'})
        self.session._notify_state_transition({'state': 'done'})
        self.assertIn(
            'action-muk_ai.action_ai_session/%d' % self.session.id,
            self.session.answer_message_id.body,
        )

    def test_a_queued_run_is_not_wrapped_up_early(self):
        self.session.write({'state': 'done', 'last_text': 'Partial.'})
        self.env['muk_ai.session.pending'].create(
            {'session_id': self.session.id, 'content': 'and one more thing'}
        )
        self.session._notify_state_transition({'state': 'done'})
        self.assertIn('Working on it', self.session.answer_message_id.body)

    def test_a_mention_is_never_able_to_stop_and_ask(self):
        self.assertEqual(self.session._effective_approval_mode(), 'off')
        self.assertNotIn('webclient', self.session._available_client_kinds())
        self.assertFalse(self.session._can_ask_user())

    def test_an_ask_user_call_is_refused_instead_of_pending(self):
        outputs = []
        call = {
            'name': 'ask_user',
            'call_id': 'call_probe',
            'arguments': {'question': 'Which one?'},
        }
        self.session._record_tool_call(call)
        self.session._skip_tool_call(
            outputs, call, 'ask_user_unavailable', log_result={'error': 'x'}
        )
        self.assertNotEqual(self.session.state, 'waiting')
        self.assertFalse(self.session.pending_ask)

    def test_the_prompt_tells_the_agent_it_cannot_ask(self):
        addenda = '\n'.join(self.session._system_prompt_addenda())
        self.assertIn('never call ask_user', addenda)

    def test_compaction_does_not_finalize_the_note_early(self):
        self.session.write({'state': 'done', 'last_text': 'Partial.'})
        self.session.with_context(
            muk_ai_skip_done_notification=True
        )._notify_state_transition({'state': 'done'})
        self.assertIn('Working on it', self.session.answer_message_id.body)

    def test_a_lost_placeholder_is_posted_at_the_end_instead(self):
        self.session.answer_message_id.unlink()
        self.session.write({'state': 'done', 'last_text': 'Recovered answer.'})
        self.session._notify_state_transition({'state': 'done'})
        self.assertTrue(self.session.answer_message_id)
        self.assertIn('Recovered answer.', self.session.answer_message_id.body)

    def test_an_ordinary_session_can_still_ask(self):
        plain = self.env['muk_ai.session'].create(
            {'name': 'Plain', 'agent_id': self.agent.id}
        )
        self.assertIn('webclient', plain._available_client_kinds())

    def test_a_linked_session_that_is_no_mention_posts_no_answer(self):
        record = self.env['res.partner'].create({'name': 'Automation Target'})
        session = self.env['muk_ai.session'].create(
            {
                'name': 'Automation Run',
                'agent_id': self.agent.id,
                'res_model': 'res.partner',
                'res_id': record.id,
            }
        )
        before = self.env['mail.message'].search_count(
            [('model', '=', 'res.partner'), ('res_id', '=', record.id)]
        )
        session.write({'state': 'done', 'last_text': 'internal-only transcript'})
        session._notify_state_transition({'state': 'done'})
        after = self.env['mail.message'].search(
            [('model', '=', 'res.partner'), ('res_id', '=', record.id)]
        )
        self.assertEqual(len(after), before)
        self.assertFalse(session.answer_message_id)
        self.assertNotIn('internal-only transcript', str(after.mapped('body')))

    def test_answering_never_enrols_the_agent_in_the_conversation(self):
        self.session.write({'state': 'done', 'last_text': 'Done.'})
        self.session._notify_state_transition({'state': 'done'})
        self.assertNotIn(
            self.agent.partner_id, self.channel.channel_member_ids.partner_id
        )
        self.assertNotIn(
            self.agent.partner_id, self.channel.message_follower_ids.partner_id
        )
