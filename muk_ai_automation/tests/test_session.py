from odoo.addons.muk_ai_automation.tests.common import (
    AutomationTestCommon,
    text_payload,
    tool_payload,
)


class TestSession(AutomationTestCommon):
    """Chats an action starts know their record, their predecessor and their trigger."""

    def test_chats_continue_per_record_only_when_asked(self):
        self.agent.system_prompt = 'About {{ record.name }}.'
        for strategy, linked in (('per_record', True), ('none', False)):
            with self.subTest(strategy=strategy):
                action = self._make_action(
                    agent_dispatch_mode='per_record',
                    agent_chain_strategy=strategy,
                    agent_record_domain=self._domain_for(self.partners[0]),
                    agent_prompt=(
                        'Before: {{ previous_session.last_text }} '
                        "{{ previous_session.tool_log[0]['name'] "
                        "if previous_session.tool_log else '' }}"
                    ),
                )
                with (
                    self._mock_responses(
                        [
                            tool_payload('search_read', {'model': 'res.partner'}),
                            text_payload('first answer'),
                        ]
                    ),
                    self._patch_tool({})[0],
                ):
                    action.run()
                _result, sent = self._run(action)
                first, second = self._sessions_of(action)
                self.assertIn('About Partner 0.', sent[0])
                self.assertEqual(
                    second.previous_session_id,
                    first if linked else self.env['muk_ai.session'],
                )
                self.assertEqual('Before: first answer search_read' in sent[0], linked)

    def test_action_chats_offer_no_browser_tools(self):
        action = self._make_action()
        self._run(action)
        chats = self.env['muk_ai.session'].create(
            {'name': 'Test chat', 'agent_id': self.agent.id}
        ) | self._sessions_of(action)
        offered = [
            'adjust_search' in {tool['name'] for tool in chat._get_filtered_catalog()}
            for chat in chats
        ]
        self.assertEqual(offered, [True, False])

    def test_automation_rule_starts_a_chat_on_the_new_record(self):
        action = self._make_action(
            agent_dispatch_mode='per_record',
            agent_prompt='Welcome {{ record.name }}.',
        )
        self.env['base.automation'].create(
            {
                'name': 'Welcome new partners',
                'model_id': action.model_id.id,
                'trigger': 'on_create',
                'action_server_ids': [(6, 0, action.ids)],
            }
        )
        self.addCleanup(self.env['base.automation']._unregister_hook)
        with self._mock_responses([text_payload('ok')]) as sent:
            partner = self.env['res.partner'].create({'name': 'Newcomer'})
        session = self._sessions_of(action)
        self.assertEqual(
            (session.res_model, session.res_id), ('res.partner', partner.id)
        )
        self.assertIn('Welcome Newcomer.', str(sent[0]['inputs']))
        self.assertIn(
            'started for this record', ''.join(partner.message_ids.mapped('body'))
        )

    def test_action_chats_land_in_their_space(self):
        custom = (
            self.env['muk_ai.space']
            .sudo()
            .create({'name': 'Partner Review', 'domain': "[('id', '=', 0)]"})
        )
        cron = self.env['ir.cron'].create(
            {
                'name': 'Weekly Review',
                'model_id': self.env['ir.model']._get_id('res.partner'),
                'state': 'ai_agent',
                'agent_id': self.agent.id,
                'agent_prompt': 'Hello.',
                'agent_record_domain': self._domain_for(self.partners),
            }
        )
        actions = (
            self._make_action(agent_dispatch_mode='per_record'),
            cron.ir_actions_server_id,
            self._make_action(agent_space_id=custom.id),
        )
        for action in actions:
            self._run(action)
        spaces = (
            self.env.ref('muk_ai_automation.space_automation'),
            self.env.ref('muk_ai_automation.space_scheduled'),
            custom,
        )
        sessions = self.env['muk_ai.session']
        chats = sessions.concat(*(self._sessions_of(action) for action in actions))
        for action, space in zip(actions, spaces, strict=True):
            with self.subTest(space=space.name):
                self.assertEqual(
                    sessions.search(space._session_domain()) & chats,
                    self._sessions_of(action),
                )
        records = self.env.ref('muk_ai_chatter.space_records')
        self.assertTrue(chats.filtered('res_id'))
        self.assertFalse(sessions.search(records._session_domain()) & chats)
        self.assertFalse(
            sessions.search(sessions.env['muk_ai.space']._unclaimed_session_domain())
            & self._sessions_of(actions[0])
        )
