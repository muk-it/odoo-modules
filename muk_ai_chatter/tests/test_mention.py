from markupsafe import Markup

from odoo.tests.common import new_test_user, tagged

from .common import ChatterTestCommon


@tagged('post_install', '-at_install', 'muk_ai_chatter')
class TestMention(ChatterTestCommon):
    """Test what mentioning an agent summons, and where it summons nothing."""

    def test_agent_has_a_stand_in_contact_without_an_email(self):
        self.assertTrue(self.agent.partner_id)
        self.assertEqual(self.agent.partner_id.name, 'Chatter Agent')
        self.assertFalse(self.agent.partner_id.email)

    def test_renaming_the_agent_renames_its_contact(self):
        self.agent.name = 'Renamed Agent'
        self.assertEqual(self.agent.partner_id.name, 'Renamed Agent')

    def test_the_stand_in_contact_is_archived_so_nothing_lists_it(self):
        self.assertFalse(self.agent.partner_id.active)

    def test_an_agent_contact_stays_out_of_pickers(self):
        found = self.env['res.partner'].name_search(name='Chatter Agent')
        self.assertNotIn(self.agent.partner_id.id, [row[0] for row in found])

    def test_an_agent_contact_stays_out_of_the_contacts_app(self):
        listed = self.env['res.partner'].search([('name', 'ilike', 'Chatter Agent')])
        self.assertNotIn(self.agent.partner_id, listed)

    def test_an_agent_is_not_offered_in_the_chatter_of_a_record(self):
        offered = self._suggested_partner_ids(
            self.env['res.partner'].get_mention_suggestions(search='Chatter Agent')
        )
        self.assertNotIn(self.agent.partner_id.id, offered)

    def test_a_mention_on_a_record_summons_no_run(self):
        with self._mute_worker() as started:
            self._mention()
        self.assertFalse(self._sessions_on(self.record))
        self.assertFalse(started)

    def test_a_mention_on_a_record_leaves_no_answer_in_the_thread(self):
        with self._mute_worker():
            self._mention()
        messages = self._messages_on(self.record)
        self.assertNotIn(self.agent.partner_id, messages.author_id)
        bodies = messages.mapped('body')
        self.assertFalse([b for b in bodies if 'Working on it' in (b or '')])

    def test_a_mention_session_is_named_after_the_agent_and_the_thread(self):
        with self._mute_dispatch():
            self._mention('Shorten it.', record=self.channel)
        sessions = self._sessions_on(self.channel)
        self.assertEqual(
            sessions.name, 'Chatter Agent on %s' % self.channel.display_name
        )

    def test_a_mention_spawns_one_session_linked_to_the_thread(self):
        with self._mute_worker() as started:
            message = self._mention(record=self.channel)
        sessions = self._sessions_on(self.channel)
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions.agent_id, self.agent)
        self.assertEqual(sessions.mention_message_id, message)
        self.assertEqual(sessions.res_model, 'discuss.channel')
        self.assertEqual(sessions.res_id, self.channel.id)
        self.assertEqual(len(started), 1)

    def test_the_session_belongs_to_whoever_wrote_the_mention(self):
        user = new_test_user(self.env, login='mention_author')
        self.channel.add_members(partner_ids=user.partner_id.ids)
        with self._mute_worker():
            self.channel.with_user(user).message_post(
                body='Have a look',
                message_type='comment',
                subtype_xmlid='mail.mt_comment',
                partner_ids=[self.agent.partner_id.id],
            )
        self.assertEqual(self._sessions_on(self.channel).user_id, user)

    def test_the_agent_is_never_a_recipient_of_the_mention(self):
        with self._mute_worker():
            message = self._mention()
        self.assertNotIn(self.agent.partner_id, message.partner_ids)

    def test_the_agent_never_becomes_a_follower(self):
        before = self.record.message_follower_ids.partner_id
        with self._mute_worker():
            self._mention()
        after = self.record.message_follower_ids.partner_id
        self.assertEqual(after, before)
        self.assertNotIn(self.agent.partner_id, after)

    def test_a_human_recipient_still_gets_the_mention(self):
        other = self.env['res.partner'].create({'name': 'Real Person'})
        with self._mute_worker():
            message = self.record.message_post(
                body='Both of you',
                message_type='comment',
                subtype_xmlid='mail.mt_comment',
                partner_ids=[self.agent.partner_id.id, other.id],
            )
        self.assertIn(other, message.partner_ids)
        self.assertNotIn(self.agent.partner_id, message.partner_ids)

    def test_the_answer_is_authored_by_the_agent_though_its_contact_is_archived(self):
        with self._mute_worker():
            self._mention(record=self.channel)
        session = self._sessions_on(self.channel)
        answer = session.answer_message_id
        self.assertTrue(answer)
        self.assertFalse(self.agent.partner_id.active)
        self.assertEqual(answer.author_id, self.agent.partner_id)
        self.assertEqual(answer.parent_id, session.mention_message_id)

    def test_a_mention_does_not_also_post_the_session_mirror_note(self):
        with self._mute_worker():
            self._mention(record=self.channel)
        bodies = self._messages_on(self.channel).mapped('body')
        self.assertFalse([b for b in bodies if 'started for this record' in (b or '')])

    def test_the_thread_snapshot_is_frozen_on_the_session(self):
        self.channel.message_post(
            body='An earlier remark',
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
        )
        with self._mute_worker():
            self._mention(record=self.channel)
        session = self._sessions_on(self.channel)
        self.assertIn('An earlier remark', session.mention_context)
        self.assertIn('DATA', session.mention_context)

    def test_the_snapshot_is_offered_to_the_model_as_thread_context(self):
        with self._mute_worker():
            self._mention(record=self.channel)
        session = self._sessions_on(self.channel)
        addenda = '\n'.join(session._system_prompt_addenda())
        self.assertIn('<thread_context>', addenda)

    def test_a_mention_is_not_capped_to_read_only_tools(self):
        with self._mute_worker():
            self._mention(record=self.channel)
        self.assertIsNone(self._sessions_on(self.channel)._enforce_tool_scope())

    def test_an_agent_that_does_not_answer_mentions_is_left_alone(self):
        self.agent.mention_enabled = False
        with self._mute_worker() as started:
            message = self._mention(record=self.channel)
        self.assertFalse(self._sessions_on(self.channel))
        self.assertFalse(started)
        self.assertNotIn(self.agent.partner_id, message.partner_ids)
        self.assertNotIn(
            self.agent.partner_id, self.channel.channel_member_ids.partner_id
        )

    def test_an_archived_agent_is_still_kept_out_of_the_recipients(self):
        self.agent.active = False
        with self._mute_worker():
            message = self._mention()
        self.assertNotIn(self.agent.partner_id, message.partner_ids)

    def test_a_tool_posting_the_mention_does_not_spawn_a_session(self):
        with self._mute_worker() as started:
            self.channel.with_context(muk_mcp_session_id=1).message_post(
                body='<p>Agent asking itself</p>',
                message_type='comment',
                subtype_xmlid='mail.mt_comment',
                partner_ids=[self.agent.partner_id.id],
            )
        self.assertFalse(self._sessions_on(self.channel))
        self.assertFalse(started)

    def test_an_empty_mention_starts_nothing(self):
        with self._mute_worker():
            self._mention(body='', record=self.channel)
        self.assertFalse(self._sessions_on(self.channel))

    def test_mentioning_two_agents_runs_each_once(self):
        second = self.env['muk_ai.agent'].create({'name': 'Second Agent'})
        with self._mute_worker() as started:
            self.channel.message_post(
                body='Both please',
                message_type='comment',
                subtype_xmlid='mail.mt_comment',
                partner_ids=[self.agent.partner_id.id, second.partner_id.id],
            )
        sessions = self._sessions_on(self.channel)
        self.assertEqual(len(sessions), 2)
        self.assertEqual(sessions.agent_id, self.agent | second)
        self.assertEqual(len(started), 2)

    def test_the_prompt_does_not_carry_the_agents_own_contact_url(self):
        chip = (
            '<a href="/odoo/res.partner/%d" class="o_mail_redirect" '
            'data-oe-id="%d" data-oe-model="res.partner">@Chatter Agent</a>'
        ) % (self.agent.partner_id.id, self.agent.partner_id.id)
        with self._mute_worker() as started:
            self.channel.message_post(
                body=Markup('<span>%s what is this record about?</span>')
                % Markup(chip),
                message_type='comment',
                subtype_xmlid='mail.mt_comment',
                partner_ids=[self.agent.partner_id.id],
            )
        prompt = started[0][1]
        self.assertNotIn('res.partner/%d' % self.agent.partner_id.id, prompt)
        self.assertIn('what is this record about?', prompt)

    def test_a_link_somebody_wrote_survives_into_the_prompt(self):
        with self._mute_worker() as started:
            self.channel.message_post(
                body=Markup('<p>See <a href="https://example.com/doc">the doc</a></p>'),
                message_type='comment',
                subtype_xmlid='mail.mt_comment',
                partner_ids=[self.agent.partner_id.id],
            )
        self.assertIn('https://example.com/doc', started[0][1])

    def test_a_customer_mentioning_an_agent_still_gets_their_message_posted(self):
        portal = new_test_user(
            self.env, login='mention_portal', groups='base.group_portal'
        )
        self.record.message_subscribe(partner_ids=portal.partner_id.ids)
        with self._mute_worker() as started:
            message = self.record.with_user(portal).message_post(
                body='Any news?',
                message_type='comment',
                subtype_xmlid='mail.mt_comment',
                partner_ids=[self.agent.partner_id.id],
            )
        self.assertTrue(message)
        self.assertFalse(started)
        self.assertFalse(self._sessions_on(self.record))
        self.assertNotIn(self.agent.partner_id, message.partner_ids)

    def test_a_message_without_a_mention_changes_nothing(self):
        with self._mute_worker() as started:
            self.channel.message_post(body='Just a note', message_type='comment')
        self.assertFalse(self._sessions_on(self.channel))
        self.assertFalse(started)
