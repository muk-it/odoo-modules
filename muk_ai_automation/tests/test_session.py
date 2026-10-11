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
        action = (
            self.env['base.automation']
            .create(
                {
                    'name': 'Welcome new partners',
                    'model_id': self.env['ir.model']._get_id('res.partner'),
                    'trigger': 'on_create',
                    'state': 'ai_agent',
                    'agent_id': self.agent.id,
                    'agent_dispatch_mode': 'per_record',
                    'agent_prompt': 'Welcome {{ record.name }}.',
                }
            )
            .action_server_id
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
