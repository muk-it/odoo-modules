from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta
from unittest.mock import patch

from freezegun import freeze_time

from odoo import Command, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tests import new_test_user
from odoo.tools import mute_logger

from odoo.addons.muk_ai.tests.common import AITestCommon, text_payload, tool_payload


class TestClientTool(AITestCommon):
    """Verify a tool the client executes pauses the turn until the client answers."""

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @contextmanager
    def _paused(self, *calls: tuple) -> Iterator[tuple[models.BaseModel, list]]:
        """Yield a chat whose first round made ``calls``, and the executed calls.

        ``browser_click`` and ``browser_gated`` run in the webclient, server
        tools answer ``{"ok": true}`` and the round after the pause says done.
        """
        with (
            self._as_client_tool('browser_click', 'browser_gated'),
            self._patch_tool() as executed,
            self._mock_responses([tool_payload(*calls), text_payload('done')]),
        ):
            session = self._session()
            session.start('click it')
            yield session, executed

    def _click(self, call_id: str) -> tuple:
        """Return a ``browser_click`` call identified by ``call_id``."""
        return ('browser_click', {'ref': call_id}, call_id)

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_a_client_tool_pauses_the_turn_until_every_action_is_answered(self):
        with self._paused(self._click('c0'), self._click('c1')) as (session, executed):
            snapshot = session.get_snapshot()
            ask = snapshot['pending_ask']
            self.assertEqual(
                (snapshot['state'], ask['kind'], ask['queues_input']),
                ('waiting', 'client_action', True),
            )
            self.assertEqual(
                [(action['call_id'], action['done']) for action in ask['actions']],
                [('c0', False), ('c1', False)],
            )
            snapshot = session.submit_client_result('c1', {'ok': 2})
            self.assertEqual(snapshot['state'], 'waiting')
            self.assertEqual(
                [action['done'] for action in snapshot['pending_ask']['actions']],
                [False, True],
            )
            self.assertEqual(self._outputs_for(session, 'c1'), [])
            snapshot = session.submit_client_result('c0', {'ok': 1})
        self.assertEqual(
            (snapshot['state'], snapshot['last_text'], snapshot['pending_ask']),
            ('done', 'done', None),
        )
        self.assertEqual(executed, [])
        self.assertEqual(
            [
                item['call_id']
                for item in session.conversation
                if item.get('type') == 'function_call_output'
            ],
            ['c0', 'c1'],
        )
        self.assertEqual(
            (self._tool_output(session, 'c0'), self._tool_output(session, 'c1')),
            ({'ok': 1}, {'ok': 2}),
        )
        for kind, call_ids in (
            ('client_action', ['c0', 'c1']),
            ('client_action_result', ['c1', 'c0']),
        ):
            with self.subTest(kind=kind):
                events = self._events(session, kind)
                self.assertEqual([event['call_id'] for event in events], call_ids)

    def test_a_batch_ends_however_the_client_answers(self):
        rejected = {'error': 'rejected', 'reason': 'gone'}
        for steps, state, outputs in (
            (
                (
                    ('reject_client_action', 'c0', 'gone'),
                    ('submit_client_result', 'c1', {'ok': True}),
                ),
                'done',
                {'c0': rejected, 'c1': {'ok': True}},
            ),
            (
                (('reject_client_action', None, 'gone'),),
                'done',
                {'c0': rejected, 'c1': rejected},
            ),
            (
                (('submit_client_result', 'c0', {'ok': True}), ('action_stop',)),
                'stopped',
                {
                    'c0': {'ok': True},
                    'c1': {'status': 'cancelled', 'reason': 'stopped_by_user'},
                },
            ),
        ):
            with (
                self.subTest(steps=steps),
                self._paused(self._click('c0'), self._click('c1')) as (session, _),
            ):
                for method, *args in steps:
                    getattr(session, method)(*args)
                self.assertEqual(session.state, state)
                self.assertEqual(
                    {
                        call_id: self._tool_output(session, call_id)
                        for call_id in outputs
                    },
                    outputs,
                )

    def test_only_the_pending_actions_of_the_owner_can_be_answered(self):
        reader = new_test_user(
            self.env, login='client-reader', groups='base.group_user'
        )
        fresh = self._session()
        with self._paused(self._click('c0'), self._click('c1')) as (session, _):
            session.submit_client_result('c0', {'ok': True})
            session.share_user_ids = [Command.link(reader.id)]
            for name, chat, method, call_id, error in (
                ('nothing pending', fresh, 'submit_client_result', 'c0', UserError),
                ('nothing to reject', fresh, 'reject_client_action', None, UserError),
                ('unknown call', session, 'submit_client_result', 'c9', UserError),
                ('answered call', session, 'submit_client_result', 'c0', UserError),
                ('answered reject', session, 'reject_client_action', 'c0', UserError),
                (
                    'reader answers',
                    session.with_user(reader),
                    'submit_client_result',
                    'c1',
                    AccessError,
                ),
                (
                    'reader rejects',
                    session.with_user(reader),
                    'reject_client_action',
                    'c1',
                    AccessError,
                ),
            ):
                with self.subTest(name), self.assertRaises(error):
                    getattr(chat, method)(call_id, {'ok': True})
            self.assertEqual(session.state, 'waiting')
            self.assertEqual(self._outputs_for(session, 'c1'), [])

    @mute_logger('odoo.addons.base.models.ir_config_parameter')
    def test_a_stale_client_action_is_rejected_by_the_cron(self):
        for name, timeout, age, swept in (
            ('default, stale', None, 3600, True),
            ('default, fresh', None, 60, False),
            ('disabled', 0, 3600, False),
            ('invalid', 'off', 3600, True),
            ('set in the settings', 45, 60, True),
        ):
            with self.subTest(name), self._paused(self._click('c0')) as (session, _):
                if timeout == 45:
                    self.env['res.config.settings'].create(
                        {'ai_client_action_timeout': timeout}
                    ).execute()
                else:
                    self._set_params({'muk_ai.client_action_timeout': timeout})
                with freeze_time(fields.Datetime.now() + timedelta(seconds=age)):
                    self.env['muk_ai.session']._cron_run_pending_sessions()
                self.assertEqual(session.state, 'done' if swept else 'waiting')
                if swept:
                    output = self._tool_output(session, 'c0')
                    self.assertEqual(output['error'], 'rejected')
                    self.assertIn('timeout', output['reason'])
                session.action_stop()

    def test_a_call_that_cannot_join_the_batch_is_skipped(self):
        gated = patch.object(
            type(self.env['muk_ai.session']),
            '_client_action_deferred',
            autospec=True,
            side_effect=lambda self_arg, call: (
                'skipped: gated' if call['name'] == 'browser_gated' else None
            ),
        )
        for name, calls, actions, reason in (
            (
                'server tool after a client tool',
                (self._click('c0'), ('search_count', {'model': 'res.partner'}, 'c1')),
                ['c0'],
                'client action pending',
            ),
            (
                'client tool after a terminating tool',
                (('open_view', {'model': 'res.partner'}, 'c0'), self._click('c1')),
                [],
                'terminating tool already ran',
            ),
            (
                'client tool an addon defers',
                (self._click('c0'), ('browser_gated', {}, 'c1')),
                ['c0'],
                'skipped: gated',
            ),
        ):
            with self.subTest(name), gated, self._paused(*calls) as (session, executed):
                pending = session.get_snapshot()['pending_ask'] or {}
                self.assertEqual(
                    [action['call_id'] for action in pending.get('actions', [])],
                    actions,
                )
                self.assertIn(reason, self._tool_output(session, 'c1')['error'])
                self.assertNotIn(calls[1][0], [call['name'] for call in executed])

    def test_only_client_kinds_someone_answers_are_offered(self):
        session_class = type(self.env['muk_ai.session'])
        for kinds, offered in (
            ({'webclient'}, False),
            ({'webclient', 'browser'}, True),
        ):
            with (
                self.subTest(kinds=kinds),
                self._as_client_tool('browser_click', kind='browser'),
                patch.object(session_class, '_available_client_kinds', lambda s: kinds),
                self._mock_responses([text_payload()]) as requests,
            ):
                self._session().start('hello')
                names = self._tools(requests[0])
                self.assertIn('adjust_search', names)
                self.assertEqual('browser_click' in names, offered)
                self.assertNotIn('browser_click', self._system_prompt(requests[0]))
        with self.assertRaises(UserError):
            self.env['muk_mcp.tool']._call('adjust_search', {}, self.env)
