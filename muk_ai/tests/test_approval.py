from __future__ import annotations

import json
from unittest.mock import patch

from odoo.exceptions import UserError

from odoo.addons.muk_ai.tests.common import AITestCommon


class TestApprovalFlow(AITestCommon):
    """Verify the end-to-end approval request and resolution flow."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls._mark_sensitive('res.partner')

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _delete_call_payload(
        self, call_id: str = 'c1', ids: list[int] | None = None
    ) -> dict:
        """Build a provider payload calling ``delete_records`` on partners."""
        args = {'model': 'res.partner', 'ids': ids or [42]}
        return {
            'text': '',
            'tool_calls': [
                {
                    'call_id': call_id,
                    'name': 'delete_records',
                    'arguments': args,
                }
            ],
            'carry_inputs': [
                {
                    'type': 'function_call',
                    'name': 'delete_records',
                    'arguments': json.dumps(args),
                    'call_id': call_id,
                }
            ],
            'usage': {'input_tokens': 2, 'output_tokens': 1},
        }

    def _text(self, text: str = 'done') -> dict:
        """Build a provider payload carrying a final assistant message."""
        return {
            'text': text,
            'tool_calls': [],
            'carry_inputs': [
                {
                    'type': 'message',
                    'content': [{'type': 'output_text', 'text': text}],
                }
            ],
            'usage': {'input_tokens': 1, 'output_tokens': 1},
        }

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_risky_dispatch_pauses_for_approval(self):
        session = self.env['muk_ai.session'].create({'name': 'approve-me'})
        with self._mock_responses([self._delete_call_payload()]):
            snapshot = session.start('delete 42')
        self.assertEqual(snapshot['state'], 'waiting')
        self.assertIsInstance(session.pending_ask, dict)
        self.assertEqual(session.pending_ask['kind'], 'approval')
        self.assertEqual(session.pending_ask['name'], 'delete_records')

    def test_approve_once_dispatches_and_resumes(self):
        session = self.env['muk_ai.session'].create({'name': 'approve-run'})
        with self._mock_responses([self._delete_call_payload()]):
            session.start('delete')
        self.assertEqual(session.state, 'waiting')
        tool_patch, calls = self._patch_tool({'delete_records': '{"success": true}'})
        with tool_patch, self._mock_responses([self._text('done')]):
            snapshot = session.approve_tool()
        self.assertEqual(snapshot['state'], 'done')
        self.assertIn('delete_records', calls)
        audit = self.env['muk_ai.approval'].search(
            [
                ('session_id', '=', session.id),
                ('decision', '=', 'approved'),
            ]
        )
        self.assertEqual(len(audit), 1)
        self.assertFalse(session.pending_ask)

    def test_reject_flows_rejected_by_user_back_to_model(self):
        session = self.env['muk_ai.session'].create({'name': 'reject'})
        with self._mock_responses([self._delete_call_payload()]):
            session.start('delete')
        captured = []

        def fake(
            self_arg,
            inputs,
            tools_schema=None,
            text_schema=None,
            on_delta=None,
            model=None,
            **kwargs,
        ):
            captured.append(list(inputs or []))
            return self._text('acknowledged')

        with patch.object(
            type(self.provider),
            '_request_responses',
            autospec=True,
            side_effect=fake,
        ):
            snapshot = session.reject_tool(reason='not now')
        self.assertEqual(snapshot['state'], 'done')
        audit = self.env['muk_ai.approval'].search(
            [
                ('session_id', '=', session.id),
                ('decision', '=', 'rejected'),
            ]
        )
        self.assertEqual(len(audit), 1)
        tool_outputs_in_conversation = [
            item
            for item in session.conversation or []
            if isinstance(item, dict) and item.get('type') == 'function_call_output'
        ]
        self.assertTrue(tool_outputs_in_conversation)
        last = tool_outputs_in_conversation[-1]
        parsed = json.loads(last.get('output') or '{}')
        self.assertEqual(parsed.get('error'), 'rejected_by_user')
        self.assertEqual(parsed.get('reason'), 'not now')

    def test_approve_for_session_auto_approves_same_signature(self):
        session = self.env['muk_ai.session'].create({'name': 'remember'})
        with self._mock_responses([self._delete_call_payload(call_id='c1', ids=[11])]):
            session.start('del 11')
        self.assertEqual(session.state, 'waiting')
        tool_patch, _calls = self._patch_tool({'delete_records': '{"success": true}'})
        with tool_patch, self._mock_responses([self._text('ok')]):
            session.approve_for_session()
        self.assertEqual(session.state, 'done')
        self.assertTrue(session.approved_signatures)

        tool_patch2, calls2 = self._patch_tool({'delete_records': '{"success": true}'})
        with (
            self._mock_responses(
                [
                    self._delete_call_payload(call_id='c2', ids=[22]),
                    self._text('auto ok'),
                ]
            ),
            tool_patch2,
        ):
            snapshot = session.send_message('del 22')
        self.assertEqual(snapshot['state'], 'done')
        self.assertIn('delete_records', calls2)
        auto = self.env['muk_ai.approval'].search(
            [
                ('session_id', '=', session.id),
                ('decision', '=', 'auto_approved'),
            ]
        )
        self.assertEqual(len(auto), 1)

    def test_approve_for_session_memory_is_scoped_to_that_session(self):
        s1 = self.env['muk_ai.session'].create({'name': 'first'})
        with self._mock_responses([self._delete_call_payload(call_id='c1', ids=[11])]):
            s1.start('del 11')
        tool_patch, _ = self._patch_tool({'delete_records': '{"success": true}'})
        with tool_patch, self._mock_responses([self._text('ok')]):
            s1.approve_for_session()

        s2 = self.env['muk_ai.session'].create({'name': 'second'})
        with self._mock_responses([self._delete_call_payload(call_id='c2', ids=[22])]):
            s2.start('del 22')
        self.assertEqual(s2.state, 'waiting')
        self.assertFalse(s2.approved_signatures)

    def test_agent_approval_mode_off_bypasses(self):
        agent = self.env['muk_ai.agent'].create(
            {
                'name': 'Fast',
                'approval_mode': 'off',
            }
        )
        session = self.env['muk_ai.session'].create(
            {
                'name': 'no-approval',
                'agent_id': agent.id,
            }
        )
        tool_patch, calls = self._patch_tool({'delete_records': '{"success": true}'})
        with (
            self._mock_responses(
                [
                    self._delete_call_payload(),
                    self._text('done'),
                ]
            ),
            tool_patch,
        ):
            snapshot = session.start('delete')
        self.assertEqual(snapshot['state'], 'done')
        self.assertIn('delete_records', calls)
        self.assertFalse(session.pending_ask)
        self.assertEqual(
            self.env['muk_ai.approval'].search_count(
                [('session_id', '=', session.id)],
            ),
            0,
        )

    def test_write_to_non_sensitive_model_does_not_trigger_approval(self):
        session = self.env['muk_ai.session'].create({'name': 'safe'})
        args = {
            'model': 'res.partner.category',
            'ids': [1],
            'values': {'name': 'harmless'},
        }
        update_payload = {
            'text': '',
            'tool_calls': [
                {
                    'call_id': 'u1',
                    'name': 'update_records',
                    'arguments': args,
                }
            ],
            'carry_inputs': [
                {
                    'type': 'function_call',
                    'name': 'update_records',
                    'arguments': json.dumps(args),
                    'call_id': 'u1',
                }
            ],
            'usage': {'input_tokens': 1, 'output_tokens': 1},
        }
        tool_patch, calls = self._patch_tool({'update_records': '{"success": true}'})
        with self._mock_responses([update_payload, self._text('ok')]), tool_patch:
            snapshot = session.start('rename tag')
        self.assertEqual(snapshot['state'], 'done')
        self.assertIn('update_records', calls)

    def test_send_message_queues_while_waiting_approval(self):
        session = self.env['muk_ai.session'].create({'name': 'blocked'})
        with self._mock_responses([self._delete_call_payload()]):
            session.start('delete')
        self.assertEqual(session.state, 'waiting')
        snapshot = session.send_message('queued while waiting')
        self.assertEqual(session.state, 'waiting')
        self.assertEqual(len(session.pending_ids), 1)
        self.assertEqual(
            session.pending_ids[0].content,
            'queued while waiting',
        )
        self.assertEqual(
            snapshot['pending_user_messages'][0]['content'],
            'queued while waiting',
        )

    def test_compact_refused_while_waiting_approval(self):
        session = self.env['muk_ai.session'].create({'name': 'no-compact'})
        with self._mock_responses([self._delete_call_payload()]):
            session.start('delete')
        self.assertEqual(session.state, 'waiting')
        with self.assertRaises(UserError):
            session.compact()

    def test_stop_clears_pending_approval(self):
        session = self.env['muk_ai.session'].create({'name': 'stop-clears'})
        with self._mock_responses([self._delete_call_payload()]):
            session.start('delete')
        self.assertEqual(session.state, 'waiting')
        session.action_stop()
        self.assertEqual(session.state, 'stopped')
        self.assertFalse(session.pending_ask)

    def test_clear_wipes_approved_signatures(self):
        session = self.env['muk_ai.session'].create({'name': 'clearable'})
        with self._mock_responses([self._delete_call_payload()]):
            session.start('del')
        tool_patch, _ = self._patch_tool({'delete_records': '{"success": true}'})
        with tool_patch, self._mock_responses([self._text('ok')]):
            session.approve_for_session()
        self.assertTrue(session.approved_signatures)
        session.clear()
        self.assertFalse(session.approved_signatures)
