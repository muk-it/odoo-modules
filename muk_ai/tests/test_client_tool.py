from __future__ import annotations

import json
from contextlib import AbstractContextManager
from datetime import timedelta
from unittest.mock import MagicMock, patch

from odoo import fields, models
from odoo.exceptions import UserError

from odoo.addons.muk_ai.tests.common import AITestCommon


class TestClientToolSeam(AITestCommon):
    """Verify the generic client-executed-tool pause/resume seam."""

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _tool_payload(self, name: str, arguments: dict, call_id: str) -> dict:
        """Build a provider payload emitting a single tool call."""
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

    def _tools_payload(self, calls: list) -> dict:
        """Build a provider payload emitting several tool calls in one round.

        :param calls: list of ``(name, arguments, call_id)`` tuples
        """
        return {
            'text': '',
            'tool_calls': [
                {
                    'call_id': call_id,
                    'name': name,
                    'arguments': arguments,
                }
                for name, arguments, call_id in calls
            ],
            'carry_inputs': [
                {
                    'type': 'function_call',
                    'name': name,
                    'arguments': json.dumps(arguments),
                    'call_id': call_id,
                }
                for name, arguments, call_id in calls
            ],
            'usage': {'input_tokens': 4, 'output_tokens': 2},
        }

    def _backdate_client_action(self, session: models.Model, hours: int = 1) -> None:
        """Shift the pending client-action registration into the past."""
        pending = dict(session.pending_ask)
        pending['registered_at'] = fields.Datetime.to_string(
            fields.Datetime.now() - timedelta(hours=hours)
        )
        session.pending_ask = pending

    def _text_payload(self, text: str) -> dict:
        """Build a provider payload emitting plain assistant text."""
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
        self, payloads: list[dict]
    ) -> AbstractContextManager[MagicMock]:
        """Patch the provider to pop one scripted payload per LLM round."""
        queue = list(payloads)

        def fake(self_arg, *args, **kwargs):
            if queue:
                return queue.pop(0)
            msg = 'exhausted scripted provider responses'
            raise AssertionError(msg)

        return patch.object(
            type(self.provider),
            '_request_responses',
            autospec=True,
            side_effect=fake,
        )

    def _track_execute(self, calls: list[str]) -> AbstractContextManager[MagicMock]:
        """Patch server tool execution to append each executed name to ``calls``."""

        def fake(self_arg, name, arguments, env, enforce_scope):
            calls.append(name)
            return 'server-ran', {}, arguments.get('model')

        return patch.object(
            type(self.env['muk_mcp.tool']),
            '_execute',
            autospec=True,
            side_effect=fake,
        )

    def _as_client_tool(self, *client_names: str) -> AbstractContextManager[MagicMock]:
        """Patch the catalog hook so the given tools are client-executed."""
        names = set(client_names)
        return patch.object(
            type(self.env['muk_ai.session']),
            '_client_tool_names',
            autospec=True,
            side_effect=lambda self_arg: names,
        )

    def _new_session(self, name: str = 'client') -> models.Model:
        """Create a fresh AI session for the test user."""
        return self.env['muk_ai.session'].create({'name': name})

    def _events(self, session: models.Model) -> list:
        """Return all persisted events for the session."""
        return session.fetch_events(limit=500)['events']

    def _outputs_for(self, session: models.Model, call_id: str) -> list:
        """Return the conversation tool outputs recorded for the call id."""
        return [
            item
            for item in (session.conversation or [])
            if isinstance(item, dict)
            and item.get('type') == 'function_call_output'
            and item.get('call_id') == call_id
        ]

    # ----------------------------------------------------------
    # Default resolver
    # ----------------------------------------------------------

    def test_default_is_client_tool_reads_meta(self):
        session = self._new_session('meta')
        catalog = [
            {'name': 'browser_click', '_meta': {'execute': 'client'}},
            {'name': 'search_count', '_meta': {'execute': 'server'}},
            {'name': 'open_view'},
        ]
        with patch.object(
            type(session),
            '_get_filtered_catalog',
            autospec=True,
            return_value=catalog,
        ):
            self.assertTrue(session._is_client_tool('browser_click'))
            self.assertFalse(session._is_client_tool('search_count'))
            self.assertFalse(session._is_client_tool('open_view'))
            self.assertFalse(session._is_client_tool('unknown'))

    # ----------------------------------------------------------
    # Client kinds
    # ----------------------------------------------------------

    def _kind_catalog(self) -> AbstractContextManager[MagicMock]:
        """Patch the registry catalog with tools of every client kind."""
        catalog = [
            {
                'name': 'browser_click',
                '_meta': {'execute': 'client', 'client': 'browser'},
            },
            {
                'name': 'adjust_search',
                '_meta': {'execute': 'client', 'client': 'webclient'},
            },
            {'name': 'bare_client', '_meta': {'execute': 'client'}},
            {'name': 'search_count', '_meta': {'execute': 'server'}},
        ]
        return patch.object(
            type(self.env['muk_mcp.tool']),
            'get_tools',
            autospec=True,
            return_value=catalog,
        )

    def test_catalog_drops_unavailable_client_kinds(self):
        session = self._new_session('kinds')
        with self._kind_catalog():
            names = {e['name'] for e in session._get_filtered_catalog()}
        self.assertEqual(names, {'adjust_search', 'search_count'})

    def test_tool_client_kind_lookup(self):
        session = self._new_session('kind-lookup')
        with self._kind_catalog():
            self.assertEqual(session._tool_client_kind('adjust_search'), 'webclient')
            # the kind is a static registration property: it resolves even for
            # tools whose kind is currently unavailable (routing must not
            # depend on visibility, e.g. on the approval-resume path)
            self.assertEqual(session._tool_client_kind('browser_click'), 'browser')
            self.assertIsNone(session._tool_client_kind('search_count'))
            self.assertIsNone(session._tool_client_kind('bare_client'))
            self.assertIsNone(session._tool_client_kind('unknown'))

    def test_visible_client_tools_promoted_to_essential(self):
        session = self._new_session('kind-essential')
        with self._kind_catalog():
            essential = session._get_essential_tool_names()
        self.assertIn('adjust_search', essential)
        self.assertNotIn('browser_click', essential)
        self.assertNotIn('bare_client', essential)

    def test_adjust_search_registered_as_webclient_tool(self):
        session = self._new_session('adjust-search')
        names = {e['name'] for e in session._get_filtered_catalog()}
        self.assertIn('adjust_search', names)
        self.assertTrue(session._is_client_tool('adjust_search'))
        self.assertEqual(session._tool_client_kind('adjust_search'), 'webclient')
        self.assertIn('adjust_search', session._get_essential_tool_names())

    def test_adjust_search_server_body_raises(self):
        with self.assertRaises(UserError):
            self.env['muk_mcp.mixin']._mcp_adjust_search()

    # ----------------------------------------------------------
    # Pause
    # ----------------------------------------------------------

    def test_client_tool_pauses_without_server_execution(self):
        session = self._new_session('pause')
        provider = self._script_provider(
            [
                self._tool_payload('browser_click', {'ref': 'e1'}, 'c0'),
                self._text_payload('Clicked it.'),
            ]
        )
        executed = []
        with (
            provider,
            self._track_execute(executed),
            self._as_client_tool('browser_click'),
        ):
            snapshot = session.start('Click the button.')
        self.assertEqual(snapshot['state'], 'waiting')
        self.assertEqual(snapshot['pending_ask']['kind'], 'client_action')
        self.assertEqual(snapshot['pending_ask']['call_id'], 'c0')
        self.assertEqual(snapshot['pending_ask']['name'], 'browser_click')
        self.assertNotIn('browser_click', executed)
        self.assertEqual(self._outputs_for(session, 'c0'), [])
        kinds = [e.get('kind') for e in self._events(session)]
        self.assertIn('client_action', kinds)

    # ----------------------------------------------------------
    # Resume
    # ----------------------------------------------------------

    def test_submit_client_result_resumes_to_done(self):
        session = self._new_session('submit')
        provider = self._script_provider(
            [
                self._tool_payload('browser_click', {'ref': 'e1'}, 'c0'),
                self._text_payload('Done clicking.'),
            ]
        )
        with provider, self._as_client_tool('browser_click'):
            session.start('Click the button.')
            snapshot = session.submit_client_result('c0', {'ok': True})
        self.assertEqual(snapshot['state'], 'done')
        self.assertIsNone(snapshot['pending_ask'])
        self.assertEqual(snapshot['last_text'], 'Done clicking.')
        outputs = self._outputs_for(session, 'c0')
        self.assertEqual(len(outputs), 1)
        self.assertEqual(json.loads(outputs[0]['output']), {'ok': True})
        kinds = [e.get('kind') for e in self._events(session)]
        self.assertIn('client_action_result', kinds)

    def test_reject_client_action_yields_error_result(self):
        session = self._new_session('reject')
        provider = self._script_provider(
            [
                self._tool_payload('browser_click', {'ref': 'e1'}, 'c0'),
                self._text_payload('Aborted.'),
            ]
        )
        with provider, self._as_client_tool('browser_click'):
            session.start('Click the button.')
            snapshot = session.reject_client_action('c0', 'user said no')
        self.assertEqual(snapshot['state'], 'done')
        outputs = self._outputs_for(session, 'c0')
        self.assertEqual(len(outputs), 1)
        self.assertEqual(
            json.loads(outputs[0]['output']),
            {'error': 'rejected', 'reason': 'user said no'},
        )

    # ----------------------------------------------------------
    # Validation
    # ----------------------------------------------------------

    def test_submit_requires_waiting_client_action(self):
        session = self._new_session('guard')
        with self.assertRaises(UserError):
            session.submit_client_result('c0', {'ok': True})

    def test_submit_rejects_mismatched_call_id(self):
        session = self._new_session('mismatch')
        provider = self._script_provider(
            [
                self._tool_payload('browser_click', {'ref': 'e1'}, 'c0'),
                self._text_payload('Done.'),
            ]
        )
        with provider, self._as_client_tool('browser_click'):
            session.start('Click the button.')
            with self.assertRaises(UserError):
                session.submit_client_result('wrong', {'ok': True})

    # ----------------------------------------------------------
    # Batch
    # ----------------------------------------------------------

    def test_client_tool_batch_registers_all(self):
        session = self._new_session('batch')
        provider = self._script_provider(
            [
                self._tools_payload(
                    [
                        ('browser_click', {'ref': 'e1'}, 'c0'),
                        ('browser_click', {'ref': 'e2'}, 'c1'),
                        ('browser_click', {'ref': 'e3'}, 'c2'),
                    ]
                ),
                self._text_payload('All clicked.'),
            ]
        )
        with provider, self._as_client_tool('browser_click'):
            snapshot = session.start('Click all three buttons.')
        self.assertEqual(snapshot['state'], 'waiting')
        pending = snapshot['pending_ask']
        self.assertEqual(pending['kind'], 'client_action')
        self.assertEqual(
            [action['call_id'] for action in pending['actions']],
            ['c0', 'c1', 'c2'],
        )
        self.assertEqual(pending['call_id'], 'c0')
        for call_id in ('c0', 'c1', 'c2'):
            self.assertEqual(self._outputs_for(session, call_id), [])

    def test_partial_submit_keeps_waiting_and_advances_cursor(self):
        session = self._new_session('partial')
        provider = self._script_provider(
            [
                self._tools_payload(
                    [
                        ('browser_click', {'ref': 'e1'}, 'c0'),
                        ('browser_click', {'ref': 'e2'}, 'c1'),
                    ]
                ),
                self._text_payload('Both clicked.'),
            ]
        )
        with provider, self._as_client_tool('browser_click'):
            session.start('Click both buttons.')
            snapshot = session.submit_client_result('c0', {'ok': True})
        self.assertEqual(snapshot['state'], 'waiting')
        pending = snapshot['pending_ask']
        self.assertEqual(pending['call_id'], 'c1')
        self.assertEqual(
            [action['done'] for action in pending['actions']], [True, False]
        )
        self.assertEqual(self._outputs_for(session, 'c0'), [])

    def test_batch_submits_resume_in_call_order(self):
        session = self._new_session('order')
        provider = self._script_provider(
            [
                self._tools_payload(
                    [
                        ('browser_click', {'ref': 'e1'}, 'c0'),
                        ('browser_click', {'ref': 'e2'}, 'c1'),
                    ]
                ),
                self._text_payload('Both clicked.'),
            ]
        )
        with provider, self._as_client_tool('browser_click'):
            session.start('Click both buttons.')
            session.submit_client_result('c1', {'ok': 2})
            snapshot = session.submit_client_result('c0', {'ok': 1})
        self.assertEqual(snapshot['state'], 'done')
        ordered = [
            item['call_id']
            for item in (session.conversation or [])
            if isinstance(item, dict)
            and item.get('type') == 'function_call_output'
            and item.get('call_id') in ('c0', 'c1')
        ]
        self.assertEqual(ordered, ['c0', 'c1'])
        self.assertEqual(
            json.loads(self._outputs_for(session, 'c0')[0]['output']), {'ok': 1}
        )

    def test_reject_all_resumes_with_errors(self):
        session = self._new_session('reject-all')
        provider = self._script_provider(
            [
                self._tools_payload(
                    [
                        ('browser_click', {'ref': 'e1'}, 'c0'),
                        ('browser_click', {'ref': 'e2'}, 'c1'),
                    ]
                ),
                self._text_payload('Aborted.'),
            ]
        )
        with provider, self._as_client_tool('browser_click'):
            session.start('Click both buttons.')
            snapshot = session.reject_client_action(reason='client gone')
        self.assertEqual(snapshot['state'], 'done')
        for call_id in ('c0', 'c1'):
            self.assertEqual(
                json.loads(self._outputs_for(session, call_id)[0]['output']),
                {'error': 'rejected', 'reason': 'client gone'},
            )

    def test_reject_single_keeps_waiting(self):
        session = self._new_session('reject-one')
        provider = self._script_provider(
            [
                self._tools_payload(
                    [
                        ('browser_click', {'ref': 'e1'}, 'c0'),
                        ('browser_click', {'ref': 'e2'}, 'c1'),
                    ]
                ),
                self._text_payload('Partly done.'),
            ]
        )
        with provider, self._as_client_tool('browser_click'):
            session.start('Click both buttons.')
            snapshot = session.reject_client_action('c0', 'element missing')
            self.assertEqual(snapshot['state'], 'waiting')
            snapshot = session.submit_client_result('c1', {'ok': True})
        self.assertEqual(snapshot['state'], 'done')
        self.assertEqual(
            json.loads(self._outputs_for(session, 'c0')[0]['output']),
            {'error': 'rejected', 'reason': 'element missing'},
        )

    def test_server_tool_after_client_batch_is_skipped(self):
        session = self._new_session('mixed')
        provider = self._script_provider(
            [
                self._tools_payload(
                    [
                        ('browser_click', {'ref': 'e1'}, 'c0'),
                        ('search_count', {'model': 'res.partner'}, 'c1'),
                    ]
                ),
                self._text_payload('Done.'),
            ]
        )
        executed = []
        with (
            provider,
            self._track_execute(executed),
            self._as_client_tool('browser_click'),
        ):
            snapshot = session.start('Click, then count.')
        self.assertEqual(snapshot['state'], 'waiting')
        self.assertEqual(
            [action['call_id'] for action in snapshot['pending_ask']['actions']],
            ['c0'],
        )
        self.assertNotIn('search_count', executed)
        outputs = self._outputs_for(session, 'c1')
        self.assertEqual(len(outputs), 1)
        self.assertIn(
            'client action pending', json.loads(outputs[0]['output'])['error']
        )

    def test_client_tool_after_terminating_is_skipped(self):
        session = self._new_session('terminating')
        provider = self._script_provider(
            [
                self._tools_payload(
                    [
                        ('open_view', {'model': 'res.partner'}, 'c0'),
                        ('browser_click', {'ref': 'e1'}, 'c1'),
                    ]
                ),
                self._text_payload('Opened the view.'),
            ]
        )
        executed = []
        with (
            provider,
            self._track_execute(executed),
            self._as_client_tool('browser_click'),
        ):
            snapshot = session.start('Open the view, then click.')
        self.assertNotEqual(snapshot['state'], 'waiting')
        self.assertIsNone(snapshot['pending_ask'])
        self.assertIn('open_view', executed)
        outputs = self._outputs_for(session, 'c1')
        self.assertEqual(len(outputs), 1)
        self.assertIn('terminating', json.loads(outputs[0]['output'])['error'])

    def test_stop_flushes_every_batch_action(self):
        session = self._new_session('stop-batch')
        provider = self._script_provider(
            [
                self._tools_payload(
                    [
                        ('browser_click', {'ref': 'e1'}, 'c0'),
                        ('browser_click', {'ref': 'e2'}, 'c1'),
                    ]
                ),
                self._text_payload('Never reached.'),
            ]
        )
        with provider, self._as_client_tool('browser_click'):
            session.start('Click both buttons.')
            session.submit_client_result('c0', {'ok': True})
            session.action_stop()
        self.assertEqual(session.state, 'stopped')
        self.assertEqual(
            json.loads(self._outputs_for(session, 'c0')[0]['output']),
            {'ok': True},
        )
        cancelled = json.loads(self._outputs_for(session, 'c1')[0]['output'])
        self.assertEqual(cancelled['status'], 'cancelled')

    def test_send_message_queues_during_client_action(self):
        session = self._new_session('queue')
        provider = self._script_provider(
            [
                self._tool_payload('browser_click', {'ref': 'e1'}, 'c0'),
                self._text_payload('Clicked.'),
            ]
        )
        with provider, self._as_client_tool('browser_click'):
            session.start('Click the button.')
            snapshot = session.send_message('Also check the totals.')
        self.assertEqual(snapshot['state'], 'waiting')
        self.assertEqual(snapshot['pending_ask']['kind'], 'client_action')
        self.assertEqual(len(session.pending_ids), 1)

    def test_deferred_client_action_is_skipped(self):
        session = self._new_session('deferred')
        provider = self._script_provider(
            [
                self._tools_payload(
                    [
                        ('browser_click', {'ref': 'e1'}, 'c0'),
                        ('browser_gated', {'ref': 'e2'}, 'c1'),
                    ]
                ),
                self._text_payload('Done.'),
            ]
        )
        deferral = patch.object(
            type(session),
            '_client_action_deferred',
            autospec=True,
            side_effect=lambda self_arg, call: (
                'skipped: gated' if call['name'] == 'browser_gated' else None
            ),
        )
        with (
            provider,
            deferral,
            self._as_client_tool('browser_click', 'browser_gated'),
        ):
            snapshot = session.start('Click, then do the gated thing.')
        self.assertEqual(snapshot['state'], 'waiting')
        self.assertEqual(
            [action['call_id'] for action in snapshot['pending_ask']['actions']],
            ['c0'],
        )
        self.assertEqual(
            json.loads(self._outputs_for(session, 'c1')[0]['output']),
            {'error': 'skipped: gated'},
        )

    # ----------------------------------------------------------
    # Timeout
    # ----------------------------------------------------------

    def test_stale_client_action_swept(self):
        session = self._new_session('stale')
        provider = self._script_provider(
            [
                self._tool_payload('browser_click', {'ref': 'e1'}, 'c0'),
                self._text_payload('Gave up.'),
            ]
        )
        with provider, self._as_client_tool('browser_click'):
            session.start('Click the button.')
            self._backdate_client_action(session)
            self.env['muk_ai.session']._sweep_stale_client_actions()
        self.assertEqual(session.state, 'done')
        result = json.loads(self._outputs_for(session, 'c0')[0]['output'])
        self.assertEqual(result['error'], 'rejected')
        self.assertIn('timeout', result['reason'])

    def test_sweep_ignores_fresh_client_action(self):
        session = self._new_session('fresh')
        provider = self._script_provider(
            [
                self._tool_payload('browser_click', {'ref': 'e1'}, 'c0'),
                self._text_payload('Never sent.'),
            ]
        )
        with provider, self._as_client_tool('browser_click'):
            session.start('Click the button.')
            self.env['muk_ai.session']._sweep_stale_client_actions()
        self.assertEqual(session.state, 'waiting')

    def test_timeout_param_falls_back_on_invalid_value(self):
        self.env['ir.config_parameter'].sudo().set_param(
            'muk_ai.client_action_timeout', 'off'
        )
        self.assertEqual(self.env['muk_ai.session']._client_action_timeout(), 600)

    def test_sweep_disabled_by_param(self):
        session = self._new_session('disabled')
        self.env['ir.config_parameter'].sudo().set_param(
            'muk_ai.client_action_timeout', '0'
        )
        provider = self._script_provider(
            [
                self._tool_payload('browser_click', {'ref': 'e1'}, 'c0'),
                self._text_payload('Never sent.'),
            ]
        )
        with provider, self._as_client_tool('browser_click'):
            session.start('Click the button.')
            self._backdate_client_action(session)
            self.env['muk_ai.session']._sweep_stale_client_actions()
        self.assertEqual(session.state, 'waiting')

    def test_build_request_inputs_closes_orphan_client_call(self):
        # Regression: a client action (e.g. open_view with target="current")
        # navigates the tab away before submit_client_result runs, leaving its
        # function_call without a function_call_output. Rebuilding the request
        # must close the orphan, else the provider rejects the input with
        # "No tool output found for function call ...".
        session = self._new_session()
        call_id = 'call_orphan_open_view'
        session.conversation = [
            {
                'type': 'message',
                'role': 'user',
                'content': [{'type': 'input_text', 'text': 'open contact olsen'}],
            },
            {
                'type': 'function_call',
                'name': 'open_view',
                'arguments': json.dumps({'model': 'res.partner', 'view_type': 'list'}),
                'call_id': call_id,
            },
        ]
        self.assertEqual(self._outputs_for(session, call_id), [])

        inputs = session._build_request_inputs()

        # The orphan gained an interrupted output, persisted on the session...
        self.assertEqual(len(self._outputs_for(session, call_id)), 1)
        # ...and no function_call in the built request is left unanswered.
        pending = {
            item['call_id']
            for item in inputs
            if isinstance(item, dict) and item.get('type') == 'function_call'
        }
        answered = {
            item['call_id']
            for item in inputs
            if isinstance(item, dict) and item.get('type') == 'function_call_output'
        }
        self.assertFalse(
            pending - answered,
            'every function_call must be paired with a function_call_output',
        )
