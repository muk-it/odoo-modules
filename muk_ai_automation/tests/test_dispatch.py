from odoo.exceptions import UserError, ValidationError
from odoo.tests import new_test_user

from odoo.addons.muk_ai_automation.tests.common import AutomationTestCommon


class TestDispatch(AutomationTestCommon):
    """Running an ``ai_agent`` action starts the chats it is configured for."""

    def test_run_starts_one_chat_or_one_per_record(self):
        cases = [
            ('single', 100, 1, 'For Partner 0, Partner 1, Partner 2.'),
            ('per_record', 100, 3, 'For Partner 2.'),
            ('per_record', 2, 2, 'For Partner 1.'),
            ('per_record', 0, 3, 'For Partner 2.'),
        ]
        for mode, limit, count, last_prompt in cases:
            with self.subTest(mode=mode, limit=limit):
                action = self._make_action(
                    agent_dispatch_mode=mode,
                    agent_max_records_per_fire=limit,
                    agent_prompt=(
                        "For {{ ', '.join((record or records).mapped('name')) }}."
                    ),
                )
                result, sent = self._run(action)
                sessions = self._sessions_of(action)
                self.assertEqual(len(sessions), count)
                self.assertEqual(action.agent_session_count, count)
                self.assertEqual(set(sessions.mapped('state')), {'done'})
                self.assertFalse(any(sessions.mapped('notification_unread')))
                self.assertEqual(sessions.user_id, self.env.ref('base.user_admin'))
                self.assertIn(last_prompt, sent[-1])
                self.assertEqual(
                    result['params']['message'],
                    'Agent Action started '
                    + ('an AI chat.' if count == 1 else f'{count} AI chats.'),
                )
                if mode == 'single':
                    self.assertFalse(sessions.res_id)
                    self.assertEqual(sessions.name, 'Agent Action')
                else:
                    self.assertEqual(
                        sessions.mapped('res_id'), self.partners[:count].ids
                    )
                    self.assertEqual(sessions[0].name, 'Agent Action - Partner 0')

    def test_records_come_from_the_trigger_else_domain_or_code(self):
        cases = [
            ({'agent_record_domain': self._domain_for(self.partners[1])}, {}, [1]),
            (
                {
                    'agent_record_source': 'code',
                    'agent_record_code': (
                        f"records = env['res.partner'].browse({self.partners[:2].ids})"
                    ),
                },
                {},
                [0, 1],
            ),
            ({'agent_record_source': 'code', 'agent_record_code': 'x = 1'}, {}, []),
            (
                {},
                {
                    'active_model': 'res.partner',
                    'active_ids': self.partners[2].ids,
                    'default_state': 'ai_agent',
                },
                [2],
            ),
        ]
        for values, context, indexes in cases:
            with self.subTest(values=values, context=context):
                action = self._make_action(agent_dispatch_mode='per_record', **values)
                result, _sent = self._run(action, **context)
                self.assertEqual(bool(result), bool(indexes))
                self.assertEqual(
                    self._sessions_of(action).mapped('res_id'),
                    [self.partners[index].id for index in indexes],
                )

    def test_invalid_record_code_is_refused(self):
        with self.assertRaises(ValidationError):
            self._make_action(
                agent_record_source='code',
                agent_record_code='records = (',
            )

    def test_run_needs_an_active_agent(self):
        archived = self.env['muk_ai.agent'].create(
            {'name': 'Archived Agent', 'active': False}
        )
        for agent in (self.env['muk_ai.agent'], archived):
            with self.subTest(agent=agent.name):
                action = self._make_action(agent_id=agent.id)
                with self.assertRaises(UserError):
                    self._run(action)
                self.assertFalse(self._sessions_of(action))

    def test_only_an_agent_action_starts_with_the_default_agent(self):
        default = self.env['muk_ai.agent']._get_default()
        for state, agent in (('ai_agent', default), ('code', self.env['muk_ai.agent'])):
            with self.subTest(state=state):
                action = (
                    self.env['ir.actions.server']
                    .with_context(default_state=state)
                    .create(
                        {
                            'name': 'From the menu',
                            'model_id': self.env['ir.model']._get_id('res.partner'),
                        }
                    )
                )
                self.assertTrue(default)
                self.assertEqual(action.agent_id, agent)

    def test_chats_run_as_the_runner_unless_a_rule_sets_the_user(self):
        runner, rule_user = (
            new_test_user(
                self.env,
                login=login,
                groups='base.group_system,base.group_partner_manager',
            )
            for login in ('automation_runner', 'automation_rule_user')
        )
        action = self._make_action()
        self._run(action.with_user(runner))
        self.env['base.automation'].create(
            {
                'name': 'Rule',
                'model_id': action.model_id.id,
                'trigger': 'on_create',
                'action_server_ids': [(6, 0, action.ids)],
                'agent_user_id': rule_user.id,
            }
        )
        self._run(action.with_user(runner))
        self.assertEqual(
            self._sessions_of(action).user_id.ids, [runner.id, rule_user.id]
        )
        rule_user.active = False
        with self.assertRaises(UserError):
            self._run(action.with_user(runner))
        self.assertEqual(len(self._sessions_of(action)), 2)

    def test_prompt_failures(self):
        action = self._make_action(agent_prompt='{{ "x" * 5000 }}')
        _result, sent = self._run(action)
        self.assertIn('x' * 4000 + '... [prompt truncated', sent[0])
        self.assertNotIn('x' * 4001, sent[0])
        broken = self._make_action(agent_prompt='{{ record.missing_field }}')
        _result, sent = self._run(broken)
        session = self._sessions_of(broken)
        self.assertFalse(sent)
        self.assertEqual(session.state, 'error')
        self.assertTrue(session.notification_unread)
        self.assertIn('could not be rendered', session.error_message)

    def test_removing_the_agent_type_deletes_its_actions_and_schedules(self):
        cron = self.env['ir.cron'].create(
            {
                'name': 'Weekly Review',
                'model_id': self.env['ir.model']._get_id('res.partner'),
                'state': 'ai_agent',
                'agent_id': self.agent.id,
            }
        )
        actions = self._make_action() | cron.ir_actions_server_id
        self.env['ir.actions.server']._fields['state'].ondelete['ai_agent'](actions)
        self.assertFalse(actions.exists())
        self.assertFalse(cron.exists())
