from __future__ import annotations

from odoo import models
from odoo.tests.common import new_test_user, tagged

from .common import ChatterTestCommon


@tagged('post_install', '-at_install', 'muk_ai_chatter')
class TestMentionDiscuss(ChatterTestCommon):
    """Test that an agent is offered and answers in a Discuss conversation."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        """Add a direct chat to mention the agent in."""
        super().setUpClass()
        cls.colleague = new_test_user(cls.env, login='mention_colleague')
        cls.chat = cls.env['discuss.channel']._get_or_create_chat(
            partners_to=cls.colleague.partner_id.ids
        )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _offered_in(self, channel: models.BaseModel) -> list[int]:
        """Return the contact ids a search for the agent offers in ``channel``."""
        return self._suggested_partner_ids(
            self.env['res.partner'].get_mention_suggestions_from_channel(
                channel_id=channel.id, search='Chatter Agent'
            )
        )

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_a_mention_in_a_channel_spawns_a_session_on_it(self):
        with self._mute_worker() as started:
            self._mention(body='What is up here?', record=self.channel)
        sessions = self._sessions_on(self.channel)
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions.res_model, 'discuss.channel')
        self.assertEqual(sessions.res_id, self.channel.id)
        self.assertTrue(sessions.is_mention)
        self.assertEqual(len(started), 1)

    def test_a_mention_in_a_direct_chat_reaches_the_agent(self):
        with self._mute_worker() as started:
            self._mention(body='Any idea?', record=self.chat)
        self.assertEqual(len(self._sessions_on(self.chat)), 1)
        self.assertEqual(len(started), 1)

    def test_the_answer_in_a_conversation_is_said_not_logged(self):
        with self._mute_worker():
            self._mention(record=self.channel)
        answer = self._sessions_on(self.channel).answer_message_id
        self.assertEqual(answer.subtype_id, self.env.ref('mail.mt_comment'))
        self.assertEqual(answer.author_id, self.agent.partner_id)

    def test_the_agent_is_no_recipient_and_joins_no_conversation(self):
        with self._mute_worker():
            message = self._mention(record=self.channel)
        self.assertNotIn(self.agent.partner_id, message.partner_ids)
        self.assertNotIn(
            self.agent.partner_id, self.channel.channel_member_ids.partner_id
        )

    def test_an_agent_answering_never_summons_another_one(self):
        with self._mute_worker():
            self.channel.message_post(
                body='Agents talking',
                author_id=self.agent.partner_id.id,
                message_type='comment',
                subtype_xmlid='mail.mt_comment',
                partner_ids=[self.agent.partner_id.id],
            )
        self.assertFalse(self._sessions_on(self.channel))

    def test_an_agent_is_suggested_in_a_conversation_it_is_no_member_of(self):
        self.assertNotIn(
            self.agent.partner_id, self.channel.channel_member_ids.partner_id
        )
        self.assertIn(self.agent.partner_id.id, self._offered_in(self.channel))

    def test_an_agent_that_cannot_answer_is_not_suggested_there_either(self):
        for field in ('mention_enabled', 'active'):
            self.agent.write({'mention_enabled': True, 'active': True})
            self.agent[field] = False
            self.assertNotIn(
                self.agent.partner_id.id,
                self._offered_in(self.channel),
                f'an agent with {field}=False is offered but would never answer',
            )

    def test_a_contact_who_is_no_member_is_still_not_suggested(self):
        outsider = self.env['res.partner'].create({'name': 'Chatter Agent Lookalike'})
        self.assertNotIn(outsider.id, self._offered_in(self.channel))

    def test_a_conversation_that_is_not_there_suggests_nothing(self):
        suggestions = self.env['res.partner'].get_mention_suggestions_from_channel(
            channel_id=0, search='Chatter Agent'
        )
        self.assertFalse(suggestions)

    def test_a_conversation_the_asker_cannot_read_suggests_nothing(self):
        private = self.env['discuss.channel'].create(
            {'name': 'Not Yours', 'channel_type': 'group'}
        )
        outsider = new_test_user(self.env, login='mention_outsider')
        suggestions = (
            self.env['res.partner']
            .with_user(outsider)
            .get_mention_suggestions_from_channel(
                channel_id=private.id, search='Chatter Agent'
            )
        )
        self.assertFalse(suggestions)

    def test_a_plain_user_is_offered_the_agent_in_their_own_channel(self):
        member = new_test_user(self.env, login='mention_member')
        self.channel.add_members(partner_ids=member.partner_id.ids)
        offered = self._suggested_partner_ids(
            self.env['res.partner']
            .with_user(member)
            .get_mention_suggestions_from_channel(
                channel_id=self.channel.id, search='Chatter Agent'
            )
        )
        self.assertIn(self.agent.partner_id.id, offered)

    def test_editing_a_message_neither_answers_again_nor_keeps_the_agent(self):
        with self._mute_worker() as started:
            message = self._mention(body='First ask', record=self.channel)
            self.assertEqual(len(started), 1)
            self.channel._message_update_content(
                message,
                body='<p>Second ask</p>',
                partner_ids=[self.agent.partner_id.id],
            )
            self.assertEqual(len(started), 1)
        self.assertEqual(len(self._sessions_on(self.channel)), 1)
        self.assertNotIn(self.agent.partner_id, message.partner_ids)

    def test_an_outsider_is_still_no_recipient_of_a_direct_chat(self):
        outsider = self.env['res.partner'].create({'name': 'Not In This Chat'})
        with self._mute_worker():
            message = self.chat.message_post(
                body='Both of you',
                message_type='comment',
                subtype_xmlid='mail.mt_comment',
                partner_ids=[self.agent.partner_id.id, outsider.id],
            )
        self.assertNotIn(outsider, message.partner_ids)
        self.assertEqual(len(self._sessions_on(self.chat)), 1)
