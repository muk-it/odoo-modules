from __future__ import annotations

from odoo.exceptions import UserError

from odoo.addons.muk_ai.tests.common import text_payload, tool_payload
from odoo.addons.muk_ai_subagents.tests.common import SubagentCase


class TestLead(SubagentCase):
    """A lead follows, directs, resumes and stops its subagents."""

    def _background(self) -> dict:
        """Build a provider round delegating one task, as the lead does by default."""
        tasks = [{'agent': 'Worker', 'objective': 'Look'}]
        return tool_payload(('delegate', {'tasks': tasks}, 'd1'))

    def test_a_background_run_reports_to_a_lead_that_moved_on(self):
        chat = self._lead_chat()
        with self._mock_responses(
            [self._background(), self._ask('Which?', 'a1'), text_payload('meanwhile')]
        ):
            chat.start('go')
        child = chat.child_session_ids
        self.assertEqual((chat.state, chat.last_text), ('done', 'meanwhile'))
        self.assertEqual((child.state, chat.awaiting_user), ('waiting', True))
        with self._mock_responses(
            [text_payload('found it'), text_payload('noted')]
        ) as requests:
            child.answer('These')
        self.assertEqual((chat.state, chat.last_text), ('done', 'noted'))
        self.assertFalse(chat.awaiting_user)
        notice = requests[1]['inputs'][-1]['content'][0]['text']
        self.assertIn(f'<subagent_report subagent="{child.id}"', notice)
        self.assertIn('found it', notice)
        self.assertFalse(child.delegation_brief['notify'])

    def test_a_lead_lets_a_failed_subagent_carry_on(self):
        chat = self._lead_chat()

        def retry(request: dict) -> dict:
            """Let the failed subagent carry on, once its id is known."""
            arguments = {
                'subagent': chat.child_session_ids.id,
                'message': 'Try again',
                'wait': True,
            }
            return tool_payload(('subagent_message', arguments, 'm1'))

        with self._mock_responses(
            [
                self._delegate('Count'),
                UserError('provider down'),
                retry,
                text_payload('recovered'),
                text_payload('all good'),
            ]
        ):
            chat.start('go')
        child = chat.child_session_ids
        self.assertEqual(self._reports(chat)[0]['stop_reason'], 'error')
        self.assertEqual(self._reports(chat, 'm1')[0]['report'], 'recovered')
        self.assertEqual((child.state, child.stop_reason), ('done', 'done'))
        self.assertEqual(chat.last_text, 'all good')

    def test_a_lead_checks_on_steers_and_stops_a_running_subagent(self):
        chat = self._lead_chat()

        def check(request: dict) -> dict:
            """Look at the subagent and stop it, once its id is known."""
            child = {'subagent': chat.child_session_ids.id}
            return tool_payload(
                ('subagent_status', {**child, 'messages': 5}, 's1'),
                ('subagent_stop', child, 'x1'),
            )

        with self._mock_responses(
            [self._background(), self._ask('Which?', 'a1'), check, text_payload('ok')]
        ):
            chat.start('go')
        child = chat.child_session_ids
        [status] = self._tool_output(chat, 's1')
        self.assertEqual(status['state'], 'waiting')
        self.assertEqual([m['role'] for m in status['messages']], ['user', 'question'])
        self.assertEqual(self._tool_output(chat, 'x1')['state'], 'stopped')
        self.assertEqual((child.state, chat.last_text), ('stopped', 'ok'))
        child.state = 'running'
        tools = self.env['muk_mcp.mixin'].with_context(muk_mcp_session_id=chat.id)
        tools._mcp_subagent_message(child.id, 'Only Europe')
        self.assertEqual(child.pending_ids.content, 'Only Europe')
        with self.assertRaisesRegex(UserError, 'No subagent'):
            tools._mcp_subagent_stop(0)
