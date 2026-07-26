from __future__ import annotations

import json
from collections.abc import Callable
from contextlib import AbstractContextManager
from unittest.mock import MagicMock, patch

from odoo import models
from odoo.exceptions import UserError

from odoo.addons.muk_ai.tests.common import AITestCommon


class TestSessionFlow(AITestCommon):
    """Verify the agent session run loop, tool dispatch, and termination."""

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _tool_payload(self, name: str, arguments: dict, call_id: str) -> dict:
        """Build a provider payload requesting a single tool call."""
        return {
            'text': '',
            'tool_calls': [
                {
                    'call_id': call_id,
                    'name': name,
                    'arguments': arguments,
                }
            ],
            'carry_inputs': [
                {
                    'type': 'function_call',
                    'name': name,
                    'arguments': json.dumps(arguments),
                    'call_id': call_id,
                }
            ],
            'usage': {'input_tokens': 4, 'output_tokens': 2},
        }

    def _text_payload(self, text: str) -> dict:
        """Build a provider payload emitting a final assistant message."""
        return {
            'text': text,
            'tool_calls': [],
            'carry_inputs': [
                {
                    'type': 'message',
                    'role': 'assistant',
                    'content': [{'type': 'output_text', 'text': text}],
                }
            ],
            'usage': {'input_tokens': 3, 'output_tokens': 1},
        }

    def _script_provider(
        self, payloads: list[dict], repeat_last: bool = False
    ) -> AbstractContextManager[MagicMock]:
        """Patch the provider to return one scripted payload per LLM round.

        :param repeat_last: keep replaying the last payload once the queue is
            empty instead of failing the test.
        """
        queue = list(payloads)

        def fake(self_arg, *args, **kwargs):
            if queue:
                return queue.pop(0)
            if repeat_last and payloads:
                return payloads[-1]
            msg = 'exhausted scripted provider responses'
            raise AssertionError(msg)

        return patch.object(
            type(self.provider),
            '_request_responses',
            autospec=True,
            side_effect=fake,
        )

    def _script_tool_results(
        self, results: dict[str, str | Callable[[], str]]
    ) -> AbstractContextManager[MagicMock]:
        """Patch tool execution to return a canned result per tool name.

        :param results: result per tool name, either a value or a callable
            evaluated at call time.
        :raise AssertionError: when the session calls a tool with no script.
        """

        def fake(self_arg, name, arguments, env, enforce_scope):
            if name not in results:
                raise AssertionError(f'unscripted tool {name!r}')
            value = results[name]
            return (value() if callable(value) else value), {}, arguments.get('model')

        return patch.object(
            type(self.env['muk_mcp.tool']),
            '_execute',
            autospec=True,
            side_effect=fake,
        )

    def _script_tool_raises(self, exc: Exception) -> AbstractContextManager[MagicMock]:
        """Patch tool execution to raise the given exception on every call."""

        def fake(self_arg, name, arguments, env, enforce_scope):
            raise exc

        return patch.object(
            type(self.env['muk_mcp.tool']),
            '_execute',
            autospec=True,
            side_effect=fake,
        )

    def _new_session(self, name: str = 'flow') -> models.BaseModel:
        """Create an empty agent session record."""
        return self.env['muk_ai.session'].create({'name': name})

    def _called_tool_names(self, session: models.BaseModel) -> list[str]:
        """Return the tool names of the session's ``tool_call`` events."""
        return [
            entry.get('name')
            for entry in session.fetch_events(limit=500)['events']
            if entry.get('kind') == 'tool_call'
        ]

    def _last_tool_result(self, session: models.BaseModel) -> dict:
        """Return the most recent ``tool_result`` event of the session."""
        return next(
            entry
            for entry in reversed(session.fetch_events(limit=500)['events'])
            if entry.get('kind') == 'tool_result'
        )

    # ----------------------------------------------------------
    # Read
    # ----------------------------------------------------------

    def test_read_tool_then_text_completes(self):
        session = self._new_session('read')
        provider = self._script_provider(
            [
                self._tool_payload(
                    'search_count',
                    {
                        'model': 'ir.module.module',
                        'domain': [['state', '=', 'installed']],
                    },
                    'c0',
                ),
                self._text_payload('You have 121 installed modules.'),
            ]
        )
        tools = self._script_tool_results({'search_count': '121'})
        with provider, tools:
            snapshot = session.start('How many modules are installed?')
        self.assertEqual(snapshot['state'], 'done')
        self.assertEqual(self._called_tool_names(session), ['search_count'])
        self.assertIn('121', snapshot['last_text'])

    def test_two_tool_rounds_then_summary(self):
        session = self._new_session('multi-read')
        provider = self._script_provider(
            [
                self._tool_payload('search_count', {'model': 'res.partner'}, 'c0'),
                self._tool_payload('search_read', {'model': 'res.partner'}, 'c1'),
                self._text_payload('5 partners; first is ACME.'),
            ]
        )
        tools = self._script_tool_results(
            {
                'search_count': '5',
                'search_read': '[{"name": "ACME"}]',
            }
        )
        with provider, tools:
            snapshot = session.start('Summarise partners.')
        self.assertEqual(snapshot['state'], 'done')
        self.assertEqual(
            self._called_tool_names(session),
            ['search_count', 'search_read'],
        )

    # ----------------------------------------------------------
    # Terminate
    # ----------------------------------------------------------

    def test_terminating_tool_completes_after_summary(self):
        session = self._new_session('terminate')
        provider = self._script_provider(
            [
                self._tool_payload('open_view', {'res_model': 'res.partner'}, 'c0'),
                self._text_payload('Opened the contacts list.'),
            ]
        )
        tools = self._script_tool_results(
            {
                'open_view': json.dumps(
                    {
                        'type': 'ir.actions.act_window',
                        'res_model': 'res.partner',
                        'view_mode': 'list,form',
                    }
                ),
            }
        )
        with provider, tools:
            snapshot = session.start('Open contacts.')
        self.assertEqual(snapshot['state'], 'done')
        self.assertIn('open_view', self._called_tool_names(session))

    # ----------------------------------------------------------
    # Ask
    # ----------------------------------------------------------

    def test_ask_user_pauses_then_answer_resumes(self):
        session = self._new_session('ask')
        provider = self._script_provider(
            [
                self._tool_payload('ask_user', {'question': 'Which one?'}, 'c0'),
                self._text_payload('Done.'),
            ]
        )
        with provider:
            snapshot = session.start('Update the invoice.')
        self.assertEqual(snapshot['state'], 'waiting')
        self.assertEqual(snapshot['pending_ask']['kind'], 'question')
        with provider:
            snapshot = session.answer('the latest one')
        self.assertEqual(snapshot['state'], 'done')
        self.assertIsNone(snapshot['pending_ask'])
        self.assertEqual(snapshot['last_text'], 'Done.')

    # ----------------------------------------------------------
    # Error
    # ----------------------------------------------------------

    def test_tool_error_is_recorded_and_loop_continues(self):
        session = self._new_session('tool-error')
        provider = self._script_provider(
            [
                self._tool_payload('search_read', {'model': 'res.partner'}, 'c0'),
                self._text_payload('That tool failed; aborting.'),
            ]
        )
        tools = self._script_tool_raises(UserError('access denied'))
        with provider, tools:
            snapshot = session.start('list partners')
        self.assertEqual(snapshot['state'], 'done')
        result = self._last_tool_result(session)['result']
        self.assertEqual(result, {'error': 'access denied'})

    # ----------------------------------------------------------
    # Approval
    # ----------------------------------------------------------

    def test_sensitive_write_pauses_for_approval_then_runs(self):
        self._mark_sensitive('res.partner')
        session = self._new_session('approval')
        provider = self._script_provider(
            [
                self._tool_payload(
                    'delete_records',
                    {
                        'model': 'res.partner',
                        'ids': [42],
                    },
                    'c0',
                ),
                self._text_payload('Deleted.'),
            ]
        )
        tools = self._script_tool_results({'delete_records': 'ok'})
        with provider, tools:
            snapshot = session.start('drop partner 42')
        self.assertEqual(snapshot['state'], 'waiting')
        self.assertEqual(snapshot['pending_ask']['kind'], 'approval')
        with provider, tools:
            snapshot = session.approve_tool()
        self.assertEqual(snapshot['state'], 'done')
        self.assertEqual(snapshot['last_text'], 'Deleted.')

    def test_sensitive_write_rejection_short_circuits_dispatch(self):
        self._mark_sensitive('res.partner')
        session = self._new_session('reject')
        provider = self._script_provider(
            [
                self._tool_payload(
                    'delete_records',
                    {
                        'model': 'res.partner',
                        'ids': [42],
                    },
                    'c0',
                ),
                self._text_payload('Aborted.'),
            ]
        )
        with provider:
            snapshot = session.start('drop partner 42')
        self.assertEqual(snapshot['state'], 'waiting')
        with provider:
            snapshot = session.reject_tool('not now')
        self.assertEqual(snapshot['state'], 'done')
        result = self._last_tool_result(session)['result']
        self.assertEqual(result['error'], 'rejected_by_user')
        self.assertEqual(result['reason'], 'not now')

    # ----------------------------------------------------------
    # Cap
    # ----------------------------------------------------------

    def test_iteration_cap_terminates_with_error(self):
        session = self._new_session('cap')
        provider = self._script_provider(
            [
                self._tool_payload('search_count', {'model': 'res.partner'}, 'c0'),
            ],
            repeat_last=True,
        )
        tools = self._script_tool_results({'search_count': '0'})
        with provider, tools:
            snapshot = session.start('count partners forever')
        self.assertEqual(snapshot['state'], 'error')
        self.assertIn('Maximum iterations', snapshot['error_message'] or '')

    # ----------------------------------------------------------
    # Effort
    # ----------------------------------------------------------

    def test_round_passes_agent_reasoning_effort(self):
        model = self._create_model(
            'gpt-5-flow-effort-test', reasoning_efforts=['low', 'medium', 'high']
        )
        agent = self.env.ref('muk_ai.agent_general')
        agent.model_id = model.id
        agent.reasoning_effort = 'low'
        session = self.env['muk_ai.session'].create(
            {'name': 'effort', 'agent_id': agent.id}
        )
        captured = {}

        def fake(self_arg, *args, **kwargs):
            captured.update(kwargs)
            return self._text_payload('ok')

        with patch.object(
            type(self.provider),
            '_request_responses',
            autospec=True,
            side_effect=fake,
        ):
            session.start('hi')
        self.assertEqual(captured.get('reasoning_effort'), 'low')
