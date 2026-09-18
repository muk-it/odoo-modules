from __future__ import annotations

from odoo import models
from odoo.tests.common import tagged

from .common import SubagentTestCommon


@tagged('post_install', '-at_install', 'muk_ai_subagents')
class TestEscalation(SubagentTestCommon):
    """Verify a subagent's approval or question surfaces on the parent."""

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls._mark_sensitive('res.partner')

    def _delete_payload(self, call_id: str = 'c1') -> dict:
        """Build a provider payload deleting a sensitive partner."""
        return self._tool_payload(
            'delete_records', {'model': 'res.partner', 'ids': [42]}, call_id
        )

    def _park_on_approval(self) -> tuple[models.Model, models.Model]:
        """Return a parent parked on one subagent awaiting approval."""
        session = self._session()
        with self._mock_responses(
            [self._delegate_payload([self._task('Delete it')]), self._delete_payload()]
        ):
            session.start('go')
        return session, session.child_session_ids

    def test_child_approval_surfaces_on_parent(self):
        session, child = self._park_on_approval()
        self.assertEqual(child.state, 'waiting')
        self.assertEqual(child.pending_ask['kind'], 'approval')
        self.assertEqual(session.state, 'waiting')
        children = session._public_pending_ask()['children']
        self.assertEqual(len(children), 1)
        self.assertEqual(children[0]['id'], child.id)
        self.assertEqual(children[0]['agent_name'], 'Test Worker')
        self.assertEqual(children[0]['waiting']['kind'], 'approval')
        self.assertEqual(children[0]['waiting']['name'], 'delete_records')
        self.assertIn('preview', children[0]['waiting'])
        self.assertTrue(session.notification_unread)
        self.assertFalse(child.notification_unread)

    def test_approval_reaches_child_and_resumes_parent(self):
        session, child = self._park_on_approval()
        tool_patch, calls = self._patch_tool({'delete_records': '{"success": true}'})
        with (
            tool_patch,
            self._mock_responses([self._text('deleted'), self._text('synthesis')]),
        ):
            child.approve_tool()
        self.assertIn('delete_records', calls)
        self.assertEqual(child.state, 'done')
        self.assertEqual(session.state, 'done')
        self.assertEqual(session.last_text, 'synthesis')
        audit = self.env['muk_ai.approval'].search(
            [('session_id', '=', child.id), ('decision', '=', 'approved')]
        )
        self.assertEqual(len(audit), 1)
        self.assertFalse(
            self.env['muk_ai.approval'].search([('session_id', '=', session.id)])
        )

    def test_rejection_lets_child_continue(self):
        session, child = self._park_on_approval()
        with self._mock_responses([self._text('skipped it'), self._text('synthesis')]):
            child.reject_tool('not now')
        self.assertEqual(child.state, 'done')
        self.assertEqual(session.state, 'done')
        results = self._delegate_outputs(session)[0]['results']
        self.assertEqual(results[0]['report'], 'skipped it')

    def test_question_surfaces_and_answer_routes_to_child(self):
        session = self._park(count=1)
        child = session.child_session_ids
        ask = session._public_pending_ask()['children'][0]['waiting']
        self.assertEqual(ask['kind'], 'question')
        self.assertEqual(ask['text'], 'Q0')
        with self._mock_responses([self._text('answered'), self._text('synthesis')]):
            child.answer('42')
        self.assertEqual(child.state, 'done')
        self.assertEqual(session.state, 'done')

    def test_permissions_intersect_with_parent(self):
        self.lead.read_only = True
        self.worker.approval_mode = 'off'
        session = self._park(count=1)
        child = session.child_session_ids
        self.assertEqual(child._enforce_tool_scope(), 'read')
        self.assertEqual(child._effective_approval_mode(), 'ask')
        self.assertEqual(child._available_client_kinds(), set())

    def test_parent_tool_filter_narrows_child(self):
        self.lead.tool_filter = ['delegate', 'search_read']
        session = self._park(count=1)
        child = session.child_session_ids
        names = {entry['name'] for entry in child._get_filtered_catalog()}
        self.assertLessEqual(names, {'search_read'})
