from datetime import timedelta
from unittest.mock import patch

from psycopg2.errors import SerializationFailure

from odoo import fields, models
from odoo.exceptions import UserError
from odoo.fields import Domain
from odoo.tests.common import tagged

from .common import SubagentTestCommon

LOST_RACE = 'could not serialize access due to concurrent update'


@tagged('post_install', '-at_install', 'muk_ai_subagents')
class TestLifecycle(SubagentTestCommon):
    """What happens to a run at its edges: the hand-off, and the cleanup."""

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _age(self, sessions, days: int) -> None:
        """Backdate these sessions past a retention cutoff."""
        stale = fields.Datetime.now() - timedelta(days=days)
        self.env.cr.execute(
            'UPDATE muk_ai_session SET write_date = %s WHERE id = ANY(%s)',
            (stale, sessions.ids),
        )
        sessions.invalidate_recordset(['write_date'])

    # ----------------------------------------------------------
    # Tests — the hand-off
    # ----------------------------------------------------------

    def test_a_parent_is_never_left_waiting_on_subagents_that_already_ended(self):
        # The subagents here finish inside the delegate call itself, which is
        # the window the park has to survive: the parent is not waiting yet
        # when they report, so it has to notice for itself that they are done.
        session = self._session()
        with self._mock_responses(
            [
                self._delegate_payload([self._task('A'), self._task('B')]),
                self._text('report A'),
                self._text('report B'),
                self._text('synthesis'),
            ]
        ):
            session.start('go')
        self.assertFalse(session.child_session_ids._live())
        self.assertNotEqual(session.state, 'waiting')
        self.assertFalse(session.pending_ask)
        self.assertEqual(len(self._delegate_outputs(session)), 1)
        self.assertEqual(len(self._events(session, 'delegation_result')), 2)

    def test_an_inline_finish_tells_the_client_the_parent_runs_again(self):
        # The park was already published as waiting; without a running event
        # the client keeps showing that until something later arrives.
        session = self._session()
        published = []
        session_cls = type(session)
        original = session_cls._publish_event

        def spy(record: models.Model, event_type: str, payload: dict) -> None:
            """Record every state event of the parent while still publishing it."""
            if record.id == session.id and event_type == 'state':
                published.append(payload['state'])
            return original(record, event_type, payload)

        with (
            patch.object(session_cls, '_publish_event', spy),
            self._mock_responses(
                [
                    self._delegate_payload([self._task('A')]),
                    self._text('report A'),
                    self._text('synthesis'),
                ]
            ),
        ):
            session.start('go')
        self.assertIn('waiting', published)
        self.assertEqual(published[published.index('waiting') + 1], 'running')
        self.assertEqual(published[-1], 'done')

    def test_a_delegate_call_that_failed_is_answered_rather_than_parked_on(self):
        session = self._session()
        with self._mock_responses(
            [
                self._delegate_payload([{'agent': 'Nobody', 'objective': 'x'}]),
                self._text('never mind'),
            ]
        ):
            session.start('go')
        self.assertFalse(session.child_session_ids)
        self.assertNotEqual(session.state, 'waiting')
        self.assertFalse(session.pending_ask)
        outputs = self._delegate_outputs(session)
        self.assertEqual(len(outputs), 1)
        self.assertIn('error', outputs[0])

    def test_a_report_that_loses_the_lock_race_is_tried_again(self):
        # A subagent also ends inside a cron sweep, where nothing replays the
        # transaction; losing the race there would drop the report for good.
        session = self._park(count=1)
        child = session.child_session_ids
        attempts = []
        deliver = type(child)._deliver_to_parent

        def flaky(record):
            """Fail the first delivery the way a lost row-lock race does."""
            attempts.append(record.id)
            if len(attempts) == 1:
                raise SerializationFailure(LOST_RACE)
            return deliver(record)

        with (
            patch.object(type(child), '_deliver_to_parent', flaky),
            patch.object(self.env.cr, 'rollback', lambda: None),
            self._mock_responses([self._text('report'), self._text('synthesis')]),
        ):
            child.answer('yes')
        self.assertEqual(len(attempts), 2)
        self.assertEqual(session.state, 'done')
        self.assertEqual(session.last_text, 'synthesis')

    # ----------------------------------------------------------
    # Tests — direction
    # ----------------------------------------------------------

    def test_a_chat_of_its_own_still_gets_a_turn_of_its_own(self):
        session = self._park(count=1)
        session.turn_cost_spent = 0.37
        session.enqueue_message('and now this')
        self.assertTrue(session.pending_ids)
        self.assertTrue(session._drain_pending_message())
        self.assertEqual(session.turn_cost_spent, 0.0)
        self.assertEqual(session.state, 'running')

    def test_direction_that_arrives_too_late_never_restarts_a_subagent(self):
        # The turn loop drains the queue once more after a subagent has
        # ended. Folding a steer in there would restart a subagent that had
        # already reported, and its siblings would wait for a run that is over.
        session = self._park(count=2)
        first, second = session.child_session_ids.sorted('id')
        first.write({'state': 'running', 'pending_ask': False})
        session.subagent_steer(first.id, 'Only look at this quarter.')
        self.assertTrue(first.pending_ids)
        first.write({'state': 'done'})
        self.assertFalse(first._drain_pending_message())
        self.assertFalse(first.pending_ids)
        self.assertEqual(first.state, 'done')
        with self._mock_responses([self._text('report B'), self._text('synthesis')]):
            second.answer('yes')
        self.assertEqual(session.state, 'done')
        self.assertEqual(session.last_text, 'synthesis')

    def test_a_subagent_that_reported_cannot_be_re_asked_while_the_run_is_open(self):
        session = self._park(count=2)
        first, second = session.child_session_ids.sorted('id')
        with self._mock_responses([self._text('report A')]):
            first.answer('yes')
        self.assertEqual(first.state, 'done')
        self.assertTrue(session._run_is_live())
        with self.assertRaises(UserError):
            session.subagent_steer(first.id, 'one more thing')
        self.assertFalse(first.pending_ids)
        self.assertEqual(second.state, 'waiting')

    def test_a_subagent_can_be_asked_for_more_once_the_run_has_ended(self):
        session = self._park(count=1)
        child = session.child_session_ids
        with self._mock_responses([self._text('report'), self._text('synthesis')]):
            child.answer('yes')
        self.assertEqual(session.state, 'done')
        self.assertFalse(session._run_is_live())
        with self._mock_responses([self._text('and one more thing')]):
            roster = session.subagent_steer(child.id, 'one more thing')
        self.assertEqual(child.last_text, 'and one more thing')
        self.assertEqual(len(roster['children']), 1)
        self.assertEqual(len(self._events(session, 'delegation_steer')), 1)

    def test_an_empty_queue_drains_to_nothing(self):
        session = self._park(count=1)
        child = session.child_session_ids
        self.assertFalse(child._drain_pending_message())

    # ----------------------------------------------------------
    # Tests — the roster and the sweep
    # ----------------------------------------------------------

    def test_a_subagent_that_ends_reports_the_roster_even_with_nothing_to_deliver(self):
        session = self._park(count=1)
        child = session.child_session_ids
        child.delegation_brief = {**child.delegation_brief, 'delivered': True}
        child.write({'state': 'done', 'pending_ask': False})
        child._on_child_finished()
        roster = session.subagent_run_snapshot()
        self.assertEqual([entry['state'] for entry in roster['children']], ['done'])

    def test_a_subagent_working_through_a_long_round_is_not_swept_as_stalled(self):
        session = self._park(count=1)
        child = session.child_session_ids
        stale = fields.Datetime.now() - timedelta(seconds=child._stall_seconds() + 60)
        child.write(
            {
                'state': 'running',
                'pending_ask': False,
                'heartbeat_at': stale,
                'claimed_at': fields.Datetime.now(),
            }
        )
        self.Session._cron_sweep_stalled_children()
        self.assertEqual(child.state, 'running')
        child.claimed_at = stale
        self.Session._cron_sweep_stalled_children()
        self.assertEqual(child.state, 'stopped')
        self.assertEqual(child.stop_reason, 'stalled')

    # ----------------------------------------------------------
    # Tests — retention
    # ----------------------------------------------------------

    def test_a_subagent_is_never_swept_out_from_under_its_parent(self):
        session = self._session()
        with self._mock_responses(
            [
                self._delegate_payload([self._task('A')]),
                self._text('report A'),
                self._text('synthesis'),
            ]
        ):
            session.start('go')
        child = session.child_session_ids
        self.assertTrue(child)
        self._age(child, 400)
        deleted, _due = self.Session._gc_sessions_older_than(
            30, Domain([('id', '=', child.id)])
        )
        self.assertEqual(deleted, 0)
        self.assertTrue(child.exists())

    def test_sweeping_a_finished_run_takes_its_subagents_with_it(self):
        session = self._session()
        with self._mock_responses(
            [
                self._delegate_payload([self._task('A')]),
                self._text('report A'),
                self._text('synthesis'),
            ]
        ):
            session.start('go')
        child = session.child_session_ids
        self._age(session | child, 400)
        self.Session._gc_sessions_older_than(30, Domain([('id', '=', session.id)]))
        self.assertFalse(session.exists())
        self.assertFalse(child.exists())
