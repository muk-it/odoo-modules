from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests.common import tagged

from .common import SubagentTestCommon
from odoo.addons.muk_ai_subagents.tools import CHILD_COLORS, STEER_MAX_QUEUED


@tagged('post_install', '-at_install', 'muk_ai_subagents')
class TestRun(SubagentTestCommon):
    """Verify the run RPCs, the stall sweep and the subagent space."""

    def test_run_snapshot_shape(self):
        session = self._park()
        snapshot = session.subagent_run_snapshot()
        self.assertEqual(
            set(snapshot), {'children', 'total_cost', 'cost_limit', 'root_id'}
        )
        self.assertEqual(snapshot['root_id'], session.id)
        self.assertEqual(snapshot['cost_limit'], 5.0)
        self.assertEqual(len(snapshot['children']), 2)
        entry = snapshot['children'][0]
        self.assertEqual(
            set(entry),
            {
                'id',
                'name',
                'agent_name',
                'color',
                'state',
                'activity',
                'elapsed',
                'cost',
                'stop_reason',
                'stuck',
                'waiting',
                'waiting_since',
                'summary',
            },
        )
        self.assertEqual(entry['state'], 'waiting')
        self.assertEqual(entry['waiting']['kind'], 'question')
        self.assertTrue(entry['waiting_since'])
        self.assertFalse(entry['stuck'])
        self.assertIn(entry['color'], CHILD_COLORS)
        child = session.child_session_ids[0]
        self.assertEqual(child.subagent_run_snapshot()['root_id'], session.id)

    def test_roster_says_a_subagent_is_going_nowhere_while_it_still_runs(self):
        session = self._park(count=1)
        child = session.child_session_ids
        self.assertFalse(child._roster_entry()['stuck'])
        child.write(
            {
                'state': 'running',
                'pending_ask': False,
                'loop_state': {'withheld': {'search_read': 2}},
            }
        )
        entry = child._roster_entry()
        self.assertTrue(entry['stuck'])
        self.assertFalse(entry['waiting_since'])
        self.assertTrue(session.subagent_run_snapshot()['children'][0]['stuck'])

    def test_direction_reaches_a_running_subagent_at_its_next_round(self):
        session = self._park(count=1)
        child = session.child_session_ids
        child.write({'state': 'running', 'pending_ask': False})
        session.subagent_steer(child.id, 'Only look at this quarter.')
        self.assertEqual(len(child.pending_ids), 1)
        steer = self._events(session, 'delegation_steer')
        self.assertEqual(len(steer), 1)
        payload = steer.payload or {}
        self.assertEqual(payload.get('id'), child.id)
        self.assertIn('this quarter', payload.get('text') or '')
        before = len(child.conversation or [])
        child.turn_cost_spent = 0.42
        self.assertTrue(child._drain_pending_message())
        self.assertFalse(child.pending_ids)
        self.assertEqual(len(child.conversation or []), before + 1)
        self.assertEqual(child.state, 'running')
        self.assertEqual(child.turn_cost_spent, 0.42)

    def test_direction_is_refused_once_a_subagent_has_ended(self):
        session = self._park(count=1)
        child = session.child_session_ids
        child.write({'state': 'done', 'pending_ask': False})
        with self.assertRaises(UserError):
            child._accept_steer('too late')

    def test_a_full_queue_refuses_more_direction(self):
        session = self._park(count=1)
        child = session.child_session_ids
        child.write({'state': 'running', 'pending_ask': False})
        for index in range(STEER_MAX_QUEUED):
            child._accept_steer(f'note {index}')
        with self.assertRaises(UserError):
            child._accept_steer('one too many')

    def test_peek_lists_the_recent_calls_oldest_first(self):
        session = self._park(count=1)
        child = session.child_session_ids
        self.assertEqual(session.subagent_peek(child.id), [])
        child._append_event(
            {'kind': 'tool_call', 'name': 'search_read', 'arguments': {'model': 'x'}}
        )
        child._append_event({'kind': 'tool_call', 'name': 'read', 'arguments': {}})
        self.assertEqual(
            session.subagent_peek(child.id),
            [
                {'name': 'search_read', 'arguments': '{"model": "x"}'},
                {'name': 'read', 'arguments': '{}'},
            ],
        )
        with self.assertRaises(UserError):
            session.subagent_peek(session.id)

    def test_stop_all_resumes_parent(self):
        session = self._park()
        with self._mock_responses([self._text('synthesis')]):
            snapshot = session.subagent_stop_all()
        self.assertEqual({c['state'] for c in snapshot['children']}, {'stopped'})
        self.assertEqual(session.state, 'done')
        results = self._delegate_outputs(session)[0]['results']
        self.assertEqual({r['stop_reason'] for r in results}, {'stopped'})

    def test_stall_sweep_stops_quiet_child_and_resumes_parent(self):
        session = self._park(count=2)
        quiet, busy = session.child_session_ids.sorted('id')
        stale = fields.Datetime.now() - timedelta(hours=1)
        now = fields.Datetime.now()
        quiet.write({'state': 'running', 'claimed_at': stale, 'heartbeat_at': stale})
        busy.write({'state': 'running', 'claimed_at': now, 'heartbeat_at': now})
        self.Session._cron_sweep_stalled_children()
        self.assertEqual(quiet.state, 'stopped')
        self.assertEqual(quiet.stop_reason, 'stalled')
        self.assertEqual(busy.state, 'running')
        self.assertEqual(session.state, 'waiting')
        busy.write({'claimed_at': stale, 'heartbeat_at': stale})
        with self._mock_responses([self._text('synthesis')]):
            self.Session._cron_sweep_stalled_children()
        self.assertEqual(busy.stop_reason, 'stalled')
        self.assertEqual(session.state, 'done')
        results = self._delegate_outputs(session)[0]['results']
        self.assertEqual({r['stop_reason'] for r in results}, {'stalled'})

    def test_stall_sweep_spares_a_subagent_still_waiting_for_a_worker(self):
        session = self._park(count=1)
        child = session.child_session_ids
        child.write(
            {
                'state': 'running',
                'claimed_at': False,
                'heartbeat_at': fields.Datetime.now() - timedelta(hours=1),
            }
        )
        self.Session._cron_sweep_stalled_children()
        self.assertEqual(child.state, 'running')
        self.assertFalse(child.stop_reason)
        self.assertEqual(session.state, 'waiting')

    def test_children_collected_by_subagent_space_only(self):
        session = self._park(count=1)
        child = session.child_session_ids
        space = self.env.ref('muk_ai_subagents.space_subagents')
        self.assertIn(child, self.Session.search(space._session_domain()))
        general = self.Session.search(self.env['muk_ai.space'].fetch_general_domain())
        self.assertIn(session, general)
        self.assertNotIn(child, general)

    def test_children_stay_quiet_and_keep_their_name(self):
        session = self._park(count=1)
        child = session.child_session_ids
        self.assertFalse(child._should_autoname())
        self.assertFalse(child._should_notify_state())
        self.assertTrue(child.name.startswith('Test Worker: Task 0'))
        self.assertTrue(session._should_notify_state())
