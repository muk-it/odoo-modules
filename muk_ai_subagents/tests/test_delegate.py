from odoo.exceptions import UserError
from odoo.tests.common import tagged

from .common import SubagentTestCommon
from odoo.addons.muk_ai_subagents.tools import CHILD_COLORS


@tagged('post_install', '-at_install', 'muk_ai_subagents')
class TestDelegate(SubagentTestCommon):
    """Verify spawning subagents through the delegate tool and its guards."""

    def test_spawn_and_parallel_completion(self):
        session = self._session()
        with self._mock_responses(
            [
                self._delegate_payload(
                    [self._task('Task one'), self._task('Task two')]
                ),
                self._text('report one'),
                self._text('report two'),
                self._text('all done'),
            ]
        ):
            session.start('go')
        self.assertEqual(session.state, 'done')
        self.assertEqual(session.last_text, 'all done')
        children = session.child_session_ids.sorted('id')
        self.assertEqual(len(children), 2)
        for child in children:
            self.assertEqual(child.parent_session_id, session)
            self.assertEqual(child.agent_id, self.worker)
            self.assertEqual(child.user_id, session.user_id)
            self.assertEqual(child.state, 'done')
            self.assertEqual(child.stop_reason, 'done')
            self.assertIn(child._child_color(), CHILD_COLORS)
            self.assertTrue(child.heartbeat_at)
        self.assertNotEqual(children[0]._child_color(), children[1]._child_color())
        outputs = self._delegate_outputs(session)
        self.assertEqual(len(outputs), 1)
        self.assertEqual(outputs[0]['status'], 'completed')
        self.assertEqual(
            [result['report'] for result in outputs[0]['results']],
            ['report one', 'report two'],
        )
        self.assertEqual(len(self._events(session, 'delegation_start')), 1)
        self.assertEqual(len(self._events(session, 'delegation_result')), 2)
        start = self._events(session, 'delegation_start').payload
        self.assertEqual([entry['id'] for entry in start['children']], children.ids)

    def test_reports_come_back_in_the_order_the_brief_named_them(self):
        # A session is ordered newest first, so without an explicit sort the
        # model reads a three-task brief backwards — and only sometimes,
        # which is worse than always.
        session = self._session()
        tasks = [self._task(f'Task {index}') for index in range(3)]
        with self._mock_responses(
            [
                self._delegate_payload(tasks),
                self._text('report 0'),
                self._text('report 1'),
                self._text('report 2'),
                self._text('all done'),
            ]
        ):
            session.start('go')
        children = session.child_session_ids.sorted('id')
        self.assertEqual(
            [child.delegation_brief['objective'] for child in children],
            ['Task 0', 'Task 1', 'Task 2'],
        )
        outputs = self._delegate_outputs(session)
        self.assertEqual(
            [result['report'] for result in outputs[0]['results']],
            ['report 0', 'report 1', 'report 2'],
        )
        start = self._events(session, 'delegation_start').payload
        self.assertEqual([entry['id'] for entry in start['children']], children.ids)

    def test_child_brief_and_prompt(self):
        session = self._session()
        with self._mock_responses(
            [
                self._delegate_payload(
                    [self._task('Count partners', output_shape='one number')]
                ),
                self._text('42'),
                self._text('done'),
            ]
        ):
            session.start('go')
        child = session.child_session_ids
        self.assertEqual(child.delegation_brief['objective'], 'Count partners')
        self.assertEqual(child.delegation_brief['output_shape'], 'one number')
        self.assertEqual(child.delegation_brief['call_id'], 'd1')
        first = child.conversation[0]['content'][0]['text']
        self.assertIn('Objective: Count partners', first)
        self.assertIn('Output shape: one number', first)
        system = child._build_request_inputs()[0]['content'][0]['text']
        self.assertIn('<subagent>', system)
        self.assertIn('You are the worker.', system)

    def test_delegate_tool_offered_only_to_delegating_agents(self):
        lead = self._session()
        self.assertIn('delegate', {e['name'] for e in lead._get_tool_schema()})
        self.assertIn(
            '<delegates>', lead._build_request_inputs()[0]['content'][0]['text']
        )
        plain = self._session(self.worker)
        self.assertNotIn('delegate', {e['name'] for e in plain._get_filtered_catalog()})
        with self.assertRaises(UserError):
            self._mixin(plain)._mcp_delegate([self._task()])

    def test_a_subagent_may_not_delegate_further(self):
        self.worker.write(
            {'allow_delegation': True, 'delegate_agent_ids': [(4, self.lead.id)]}
        )
        session = self._park(count=1)
        child = session.child_session_ids
        self.assertFalse(child._can_delegate())
        self.assertNotIn('delegate', {e['name'] for e in child._get_filtered_catalog()})
        with self.assertRaises(UserError):
            self._mixin(child)._mcp_delegate([{'agent': 'Test Lead', 'objective': 'x'}])

    def test_rejects_agent_outside_whitelist(self):
        session = self._session()
        with self.assertRaises(UserError):
            self._mixin(session)._mcp_delegate(
                [{'agent': 'Test Lead', 'objective': 'x'}]
            )

    def test_rejects_bad_task_shapes(self):
        session = self._session()
        with self.assertRaises(UserError):
            self._mixin(session)._mcp_delegate([])
        with self.assertRaises(UserError):
            self._mixin(session)._mcp_delegate([self._task()] * 6)
        with self.assertRaises(UserError):
            self._mixin(session)._mcp_delegate([{'agent': 'Test Worker'}])

    def test_rejects_a_task_that_is_not_an_object_at_all(self):
        session = self._session()
        for task in ('Test Worker', 42, None, ['Test Worker']):
            with self.assertRaises(UserError):
                self._mixin(session)._mcp_delegate([task])

    def test_an_agent_may_be_named_by_id_as_well_as_by_name(self):
        session = self._session()
        with self._mock_responses(
            [
                self._delegate_payload(
                    [{'agent': str(self.worker.id), 'objective': 'Find things'}]
                ),
                self._text('report'),
                self._text('done'),
            ]
        ):
            session.start('go')
        self.assertEqual(session.child_session_ids.agent_id, self.worker)

    def test_rejects_an_agent_named_by_nothing(self):
        session = self._session()
        for agent in (None, '', '   ', 3.5):
            with self.assertRaises(UserError):
                self._mixin(session)._mcp_delegate([{'agent': agent, 'objective': 'x'}])

    def test_rejects_a_call_from_outside_any_session(self):
        mixin = self.env['muk_mcp.mixin'].with_context(muk_ai_delegate_call_id='d1')
        with self.assertRaises(UserError):
            mixin._mcp_delegate([self._task()])

    def test_rejects_a_call_from_a_session_that_is_gone(self):
        session = self._session()
        mixin = self._mixin(session)
        session.unlink()
        with self.assertRaises(UserError):
            mixin._mcp_delegate([self._task()])

    def test_rejects_call_through_tool_load(self):
        session = self._session()
        mixin = self.env['muk_mcp.mixin'].with_context(muk_mcp_session_id=session.id)
        with self.assertRaises(UserError):
            mixin._mcp_delegate([self._task()])

    def test_concurrency_cap(self):
        session = self._session()
        self.Session.with_context(muk_ai_subagent_spawn=True).create(
            [
                {
                    'name': f'busy {index}',
                    'agent_id': self.worker.id,
                    'parent_session_id': session.id,
                    'state': 'running',
                }
                for index in range(5)
            ]
        )
        with self.assertRaises(UserError):
            self._mixin(session)._mcp_delegate([self._task()])

    def test_budget_blocks_new_subagents(self):
        self.env['ir.config_parameter'].sudo().set_param(
            'muk_ai_subagents.run_cost_limit', '0.5'
        )
        session = self._session()
        session.total_cost = 1.0
        with self.assertRaises(UserError):
            self._mixin(session)._mcp_delegate([self._task()])

    def test_child_turn_cost_limit_follows_run_budget(self):
        self.env['ir.config_parameter'].sudo().set_param(
            'muk_ai_subagents.run_cost_limit', '0.5'
        )
        session = self._park(count=1)
        child = session.child_session_ids
        session.total_cost, child.total_cost, child.turn_cost_spent = 0.2, 0.1, 0.1
        self.assertAlmostEqual(child._turn_cost_limit(), 0.3)
        session.total_cost = 0.6
        self.assertAlmostEqual(child._turn_cost_limit(), 0.1)
        self.assertLessEqual(child._turn_cost_limit(), child.turn_cost_spent)

    def test_child_deadline_never_exceeds_parents(self):
        session = self._park(count=1)
        child = session.child_session_ids
        full = self.Session._turn_wallclock_seconds()
        session.turn_wallclock_spent = 100.0
        self.assertEqual(child._turn_wallclock_seconds(), full - 100)

    def test_children_do_not_count_against_rate_limit(self):
        self.provider.sudo().rate_limit = 2
        session = self._park(count=2)
        self.assertEqual(len(session.child_session_ids), 2)
        self._session()
        with self.assertRaises(UserError):
            self._session()
