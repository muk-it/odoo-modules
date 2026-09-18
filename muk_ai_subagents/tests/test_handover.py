from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests.common import new_test_user, tagged

from .common import SubagentTestCommon


@tagged('post_install', '-at_install', 'muk_ai_subagents')
class TestHandover(SubagentTestCommon):
    """A run follows its parent through a handover and a read-only share."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.owner = new_test_user(cls.env, login='sub_ho_owner')
        cls.heir = new_test_user(cls.env, login='sub_ho_heir')
        cls.reader = new_test_user(cls.env, login='sub_ho_reader')
        cls.stranger = new_test_user(cls.env, login='sub_ho_stranger')

    # ----------------------------------------------------------
    # Tests — handover
    # ----------------------------------------------------------

    def test_the_new_owner_reads_the_run_and_its_subagents(self):
        session = self._park(count=1, user=self.owner)
        child = session.child_session_ids
        session.action_handover(self.heir.id)
        self.assertEqual(child.user_id, self.owner)
        roster = session.with_user(self.heir).subagent_run_snapshot()
        self.assertEqual([entry['id'] for entry in roster['children']], [child.id])
        self.assertEqual(roster['children'][0]['waiting']['kind'], 'question')
        self.assertEqual(roster['children'][0]['activity'], 'Waiting for your decision')
        self.assertTrue(child.with_user(self.heir).get_snapshot()['events'])
        # A subagent that has only asked something has called no tool yet.
        self.assertEqual(session.with_user(self.heir).subagent_peek(child.id), [])
        child.sudo()._append_event(
            {
                'kind': 'tool_call',
                'name': 'search_read',
                'arguments': {'model': 'res.partner'},
            }
        )
        peek = session.with_user(self.heir).subagent_peek(child.id)
        self.assertEqual([call['name'] for call in peek], ['search_read'])

    def test_the_new_owner_steers_and_stops_subagents_through_the_parent(self):
        session = self._park(count=2, user=self.owner)
        first, second = session.child_session_ids.sorted('id')
        session.action_handover(self.heir.id)
        heir_session = session.with_user(self.heir)
        heir_session.subagent_steer(first.id, 'Only this quarter.')
        self.assertEqual(len(first.sudo().pending_ids), 1)
        self.assertEqual(len(self._events(session, 'delegation_steer')), 1)
        heir_session.subagent_stop(first.id)
        self.assertEqual(first.state, 'stopped')
        self.assertEqual(session.state, 'waiting')
        with self._mock_responses([self._text('synthesis')]):
            heir_session.subagent_stop_all()
        self.assertEqual(second.state, 'stopped')
        self.assertEqual(session.state, 'done')
        self.assertEqual(session.user_id, self.heir)

    def test_stopping_the_parent_as_its_new_owner_stops_its_subagents(self):
        session = self._park(count=2, user=self.owner)
        session.action_handover(self.heir.id)
        session.with_user(self.heir).action_stop()
        self.assertEqual(session.state, 'stopped')
        self.assertEqual(set(session.child_session_ids.mapped('state')), {'stopped'})

    def test_the_new_owner_answers_a_subagent_that_asked(self):
        session = self._park(count=1, user=self.owner)
        child = session.child_session_ids
        session.action_handover(self.heir.id)
        with self._mock_responses([self._text('report'), self._text('synthesis')]):
            child.with_user(self.heir).answer('42')
        self.assertEqual(child.state, 'done')
        self.assertEqual(session.state, 'done')
        self.assertEqual(session.last_text, 'synthesis')

    def test_a_subagent_finishing_in_the_old_owners_worker_resumes_the_new_owner(self):
        # The child's worker keeps the user it was spawned under, so the
        # finish runs as the previous owner, who may only read the parent now.
        session = self._park(count=1, user=self.owner)
        child = session.child_session_ids
        session.action_handover(self.heir.id)
        with self._mock_responses([self._text('report'), self._text('synthesis')]):
            child.with_user(self.owner).answer('42')
        self.assertEqual(child.state, 'done')
        self.assertEqual(session.state, 'done')
        self.assertEqual(session.user_id, self.heir)
        results = self._delegate_outputs(session)[0]['results']
        self.assertEqual([entry['report'] for entry in results], ['report'])

    def test_a_parked_run_resumes_under_the_new_owners_companies(self):
        # The parent stored the previous owner's companies; the heir has one
        # of them, so a resume carrying the old context would be refused.
        other = self.env['res.company'].create({'name': 'Other Co'})
        self.owner.sudo().company_ids = [(4, other.id)]
        allowed = [self.env.company.id, other.id]
        session = (
            self.Session.with_user(self.owner)
            .with_context(allowed_company_ids=allowed)
            .create({'name': 'lead chat', 'agent_id': self.lead.id})
        )
        with self._mock_responses(
            [self._delegate_payload([self._task()]), self._ask_payload('Q', 'a0')]
        ):
            session.start('go')
        self.assertEqual(session.user_context['allowed_company_ids'], allowed)
        session.action_handover(self.heir.id)
        child = session.child_session_ids
        with self._mock_responses([self._text('report'), self._text('synthesis')]):
            child.with_user(self.owner).answer('42')
        self.assertEqual(child.state, 'done')
        self.assertEqual(session.state, 'done')
        self.assertEqual(session.last_text, 'synthesis')
        self.assertEqual(
            session.user_context['allowed_company_ids'], [self.env.company.id]
        )

    def test_the_stall_sweep_still_reports_to_a_parent_that_changed_hands(self):
        session = self._park(count=1, user=self.owner)
        child = session.child_session_ids
        session.action_handover(self.heir.id)
        stale = fields.Datetime.now() - timedelta(hours=1)
        child.write({'state': 'running', 'claimed_at': stale, 'heartbeat_at': stale})
        with self._mock_responses([self._text('synthesis')]):
            self.Session._cron_sweep_stalled_children()
        self.assertEqual(child.stop_reason, 'stalled')
        self.assertEqual(session.state, 'done')

    def test_the_previous_owner_keeps_reading_the_run_but_may_not_steer_it(self):
        session = self._park(count=1, user=self.owner)
        child = session.child_session_ids
        session.action_handover(self.heir.id)
        self.assertTrue(session.subagent_run_snapshot()['children'])
        with self.assertRaises(AccessError):
            session.subagent_steer(child.id, 'more')
        with self.assertRaises(AccessError):
            session.subagent_stop(child.id)

    # ----------------------------------------------------------
    # Tests — share
    # ----------------------------------------------------------

    def test_a_reader_of_the_parent_opens_a_subagent_but_cannot_steer_it(self):
        session = self._park(count=1, user=self.owner)
        child = session.child_session_ids
        session.share_user_ids = [(4, self.reader.id)]
        reader_session = session.with_user(self.reader)
        reader_child = child.with_user(self.reader)
        self.assertEqual(
            self.Session.with_user(self.reader).search([('id', '=', child.id)]), child
        )
        self.assertTrue(reader_child.get_snapshot()['events'])
        public = reader_session._public_pending_ask()
        self.assertEqual([entry['id'] for entry in public['children']], [child.id])
        roster = reader_session.subagent_run_snapshot()
        self.assertEqual(roster['children'][0]['activity'], 'Waiting for your decision')
        refused = (
            lambda: reader_child.write({'name': 'renamed'}),
            lambda: reader_child.answer('42'),
            reader_child.action_stop,
            lambda: reader_session.subagent_steer(child.id, 'more'),
            lambda: reader_session.subagent_stop(child.id),
            reader_session.subagent_stop_all,
        )
        for attempt in refused:
            with self.assertRaises(AccessError):
                attempt()
        self.assertEqual(child.state, 'waiting')

    def test_a_stranger_to_the_run_cannot_reach_its_subagents(self):
        session = self._park(count=1, user=self.owner)
        child = session.child_session_ids
        self.assertFalse(
            self.Session.with_user(self.stranger).search(
                [('id', 'in', (session | child).ids)]
            )
        )
        with self.assertRaises(AccessError):
            child.with_user(self.stranger).read(['name'])
        with self.assertRaises(AccessError):
            child.with_user(self.stranger).fetch_events()
        with self.assertRaises(AccessError):
            session.with_user(self.stranger).subagent_run_snapshot()

    def test_subagents_stay_out_of_the_chat_list_for_everyone_who_sees_the_run(self):
        session = self._park(count=1, user=self.owner)
        child = session.child_session_ids
        session.share_user_ids = [(4, self.reader.id)]
        session.action_handover(self.heir.id)
        for user in (self.heir, self.reader, self.owner):
            general = self.env['muk_ai.space'].with_user(user).fetch_general_domain()
            listed = self.Session.with_user(user).search(general)
            self.assertNotIn(child, listed)
        # The heir owns it, so it sits in the loose list; the reader and the
        # previous owner reach it through "Shared with Me" instead.
        heir_general = (
            self.env['muk_ai.space'].with_user(self.heir).fetch_general_domain()
        )
        self.assertIn(session, self.Session.with_user(self.heir).search(heir_general))
        shared = self.env.ref('muk_ai.space_shared')
        for user in (self.reader, self.owner):
            collected = self.Session.with_user(user).search(
                shared.with_user(user)._session_domain()
            )
            self.assertIn(session, collected)
            self.assertNotIn(child, collected)
