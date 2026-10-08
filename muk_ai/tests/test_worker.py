from __future__ import annotations

import json
import time
from contextlib import ExitStack, nullcontext
from datetime import datetime, timedelta
from operator import methodcaller
from unittest.mock import patch

import psycopg2

from odoo import Command, models, modules
from odoo.exceptions import UserError
from odoo.tests import HttpCase, new_test_user
from odoo.tools import config

from odoo.addons.muk_ai.models import ir_http as ir_http_module
from odoo.addons.muk_ai.models import session_worker
from odoo.addons.muk_ai.tests.common import AITestCommon, text_payload, tool_payload
from odoo.addons.muk_ai.tools.runtime import DISPATCH_MAX_TURNS

USER = {'role': 'user', 'content': [{'type': 'input_text', 'text': 'go'}]}
CALL = {
    'type': 'function_call',
    'name': 'search_count',
    'arguments': '{}',
    'call_id': 'c1',
}


class FakeRequest:
    """Stand in for the HTTP request a turn is queued on."""

    def __init__(self, bound: bool) -> None:
        """Remember whether a request is bound to the thread."""
        self.bound = bound

    def __bool__(self) -> bool:
        """Tell whether a request is bound, as the werkzeug proxy does."""
        return self.bound


class TestWorker(AITestCommon):
    """Verify the cron worker, its recovery sweeps, its locks and inline dispatch."""

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _run_worker(self, *payloads) -> list[dict]:
        """Run the worker cron once against the given provider rounds.

        :return: the requests the provider received
        """
        self.env.flush_all()
        with self._mock_responses(list(payloads)) as requests:
            self.env['muk_ai.session']._cron_run_pending_sessions()
        self.env.invalidate_all()
        return requests

    def _reasons(self, session: models.BaseModel) -> list[str]:
        """Return why each output closing the call ``c1`` was written."""
        return [
            json.loads(item['output'])['reason']
            for item in self._outputs_for(session, 'c1')
        ]

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_the_worker_runs_the_turn_as_its_owner(self):
        branch = self.env['res.company'].create({'name': 'Worker Branch'})
        owner = new_test_user(
            self.env,
            login='ai_worker_owner',
            groups='base.group_user',
            company_ids=[Command.set([self.env.company.id, branch.id])],
        )
        session = (
            self.env['muk_ai.session']
            .with_user(owner)
            .with_context(
                allowed_company_ids=[branch.id],
                tz='Europe/Vienna',
                stamp=datetime(2026, 1, 1),
                owner=owner,
            )
            .create({'name': 'branch turn'})
        )
        with self._mock_responses([text_payload()]):
            session.send_message('hello')
        session.sudo().write({'state': 'running'})
        with self._patch_tool() as calls:
            self._run_worker(
                tool_payload(('search_count', {'model': 'res.partner'})),
                text_payload('done'),
            )
        context = calls[0]['context']
        self.assertEqual(
            (context['allowed_company_ids'], context['tz']),
            ([branch.id], 'Europe/Vienna'),
        )
        self.assertFalse({'stamp', 'owner'} & set(context))
        self.assertEqual(
            (session.sudo().state, session.sudo().log_ids.user_id), ('done', owner)
        )

    def test_the_worker_cron_runs_one_pending_session_per_run(self):
        other = new_test_user(
            self.env, login='ai_worker_other', groups='base.group_user'
        )
        settled = [
            self._session(state=state, conversation=[USER])
            for state in ('new', 'waiting', 'stopped', 'error', 'done')
        ]
        running = self._session(state='running', conversation=[USER], user_id=other.id)
        compacting = self._session(state='compacting', conversation=[USER])
        action = self.env.ref('muk_ai.cron_run_pending_sessions_1').ir_actions_server_id
        self.env.flush_all()
        pending = []
        with self._mock_responses([text_payload('worker answer')]) as requests:
            for _run in range(2):
                action.run()
                self.env.invalidate_all()
                pending.append(
                    len(
                        (running | compacting).filtered(
                            lambda s: s.state in ('running', 'compacting')
                        )
                    )
                )
        self.assertEqual(pending, [1, 0])
        self.assertEqual(
            (running.state, running.last_text, len(requests)),
            ('done', 'worker answer', 1),
        )
        self.assertEqual(compacting.state, 'done')
        self.assertEqual(
            [s.state for s in settled], ['new', 'waiting', 'stopped', 'error', 'done']
        )

    def test_a_message_to_a_stuck_turn_recovers_it(self):
        for label, age, held, state, queued, reasons in (
            ('stale and unclaimed', 5, False, 'done', [], ['previous turn timed out']),
            ('stale but a worker holds it', 5, True, 'running', ['still there?'], []),
            ('fresh', 0, False, 'running', ['still there?'], []),
        ):
            with self.subTest(label):
                session = self._session(state='running', conversation=[USER, CALL])
                self._backdate(session, timedelta(minutes=age), 'write_date')
                with (
                    self._hold_lock(session.id) if held else nullcontext(),
                    self._mock_responses([text_payload('back')]),
                ):
                    snapshot = session.send_message('still there?')
                self.assertEqual(snapshot['state'], state)
                self.assertEqual(
                    [m['content'] for m in snapshot['pending_user_messages']], queued
                )
                self.assertEqual(self._reasons(session), reasons)

    def test_the_cron_sweeps_abandoned_turns(self):
        self.env['muk_ai.session']._session_worker_crons().write({'active': False})
        rows = (
            (
                'picked up by the worker',
                'running',
                10,
                10,
                False,
                'done',
                'tool result missing',
            ),
            (
                'abandoned',
                'running',
                5,
                5,
                False,
                'error',
                'worker abandoned the session',
            ),
            (
                'abandoned compaction',
                'compacting',
                5,
                5,
                False,
                'error',
                'worker abandoned the session',
            ),
            ('held by a worker', 'running', 5, 5, True, 'running', None),
            (
                'compaction held by a worker',
                'compacting',
                5,
                5,
                True,
                'compacting',
                None,
            ),
            ('recent heartbeat', 'running', 5, 0, False, 'running', None),
            ('recent write', 'running', 0, 0, False, 'running', None),
        )
        sessions = []
        with ExitStack() as stack:
            for _label, state, written, claimed, held, _state, _reason in rows:
                session = self._session(state=state, conversation=[USER, CALL])
                self._backdate(session, timedelta(minutes=written), 'write_date')
                self._backdate(session, timedelta(minutes=claimed), 'claimed_at')
                stack.enter_context(
                    self._hold_lock(session.id) if held else nullcontext()
                )
                sessions.append(session)
            self._run_worker(text_payload('done'))
        for (label, *_row, state, reason), session in zip(rows, sessions, strict=True):
            with self.subTest(label):
                self.assertEqual(session.state, state)
                self.assertEqual(self._reasons(session), [reason] if reason else [])

    def test_a_held_session_lock_blocks_the_worker_and_steering(self):
        self._mark_sensitive('res.partner')
        queued = self._session(state='running', conversation=[USER])
        with self._hold_lock(queued.id):
            self.assertEqual(self._run_worker(), [])
        self.assertEqual(queued.state, 'running')
        clicking, deleting = self._session(), self._session()
        with (
            self._as_client_tool('browser_click'),
            self._patch_tool() as calls,
            self._mock_responses(
                [
                    tool_payload(('browser_click', {'ref': 'e1'}, 'k1')),
                    tool_payload(
                        ('delete_records', {'model': 'res.partner', 'ids': [42]}, 'd1')
                    ),
                    text_payload('clicked'),
                    text_payload('deleted'),
                ]
            ),
        ):
            clicking.send_message('click it')
            deleting.send_message('delete it')
            for session, call_id, steer in (
                (
                    clicking,
                    'k1',
                    methodcaller('submit_client_result', 'k1', {'ok': True}),
                ),
                (deleting, 'd1', methodcaller('approve_tool')),
            ):
                with self.subTest(steer=steer):
                    with (
                        self._hold_lock(session.id),
                        self.assertRaisesRegex(UserError, 'busy'),
                    ):
                        steer(session)
                    self.assertEqual(
                        (session.state, self._outputs_for(session, call_id)),
                        ('waiting', []),
                    )
                    self.assertEqual(steer(session)['state'], 'done')
                    with self._hold_lock(session.id):
                        self.assertEqual(len(self._outputs_for(session, call_id)), 1)
        self.assertEqual([call['name'] for call in calls], ['delete_records'])

    def test_a_worker_failure_marks_the_session_error(self):
        session = self._session(state='running', conversation=[USER, CALL])
        self._run_worker(RuntimeError('provider down'))
        self.assertEqual(
            (session.state, session.error_message), ('error', 'provider down')
        )
        self.assertEqual(self._reasons(session), ['provider down'])

    def test_a_superseded_turn_wakes_another_worker(self):
        session = self._session(state='running', conversation=[USER])
        triggers = self.env['ir.cron.trigger'].search_count([])

        def replaced(request: dict) -> dict:
            """Stop the turn and ask again while its answer still streams."""
            session.action_stop()
            session.send_message('new question')
            request['on_delta']('text', {'delta': 'stale'})
            return text_payload('stale')

        self._run_worker(replaced, text_payload('new answer'))
        self.assertEqual(self.env['ir.cron.trigger'].search_count([]), triggers + 1)
        self.assertEqual(session.state, 'running')

    def test_a_turn_is_queued_on_the_request_by_dispatch_mode(self):
        first, second = self._session(), self._session()
        both = (first.id, second.id)
        for mode, workers, bound, queued in (
            ('', 0, True, both),
            ('inline', 0, True, both),
            ('cron', 0, True, ()),
            ('inline', 4, True, ()),
            ('', 2, True, ()),
            ('inline', 0, False, ()),
        ):
            with self.subTest(mode=mode, workers=workers, bound=bound):
                self._set_params({'muk_ai.dispatch_mode': mode})
                request = FakeRequest(bound)
                with (
                    patch.object(modules.module, 'current_test', None),
                    patch.object(session_worker, 'request', request),
                    patch.dict(config.options, {'workers': workers}),
                ):
                    (first | second)._trigger_worker()
                    first._trigger_worker()
                self.assertEqual(getattr(request, 'muk_ai_dispatch_ids', ()), queued)
                self.assertEqual((first.state, second.state), ('new', 'new'))

    def test_queued_turns_run_after_the_response(self):
        first, second = (
            self._session(
                state='running',
                conversation=[
                    {'role': 'user', 'content': [{'type': 'input_text', 'text': text}]}
                ],
            )
            for text in ('first', 'second')
        )
        run = self.env['ir.http']._run_queued_turns
        self.env.flush_all()
        with ExitStack() as slots, self._mock_responses([text_payload()]) as requests:
            for slot in range(-1, -DISPATCH_MAX_TURNS - 1, -1):
                slots.enter_context(self._hold_lock(slot))
            run(self.env.cr.dbname, (second.id, first.id))
        self.assertEqual(requests, [])
        with self._mock_responses(
            [text_payload('one'), text_payload('two')]
        ) as requests:
            run(self.env.cr.dbname, (second.id, first.id))
        self.env.invalidate_all()
        self.assertEqual(
            [request['inputs'][-1]['content'][0]['text'] for request in requests],
            ['second', 'first'],
        )
        with self._hold_lock(-1):
            self.assertEqual((second.last_text, first.last_text), ('one', 'two'))
        with (
            patch.object(
                ir_http_module,
                'Registry',
                side_effect=psycopg2.OperationalError('gone'),
            ),
            self.assertLogs(ir_http_module.__name__, 'ERROR') as logs,
        ):
            run('muk-ai-lost', (first.id,))
        self.assertIn('Inline AI dispatch failed', logs.output[0])


class TestRequestThreadBudget(HttpCase):
    """Verify a turn runs to its end in a request thread and slices on a cron."""

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _answer(self, provider: models.BaseModel, inputs: list, **kwargs) -> dict:
        """Answer a turn's first round slowly with a tool call, the next with text."""
        if any(item.get('type') == 'function_call_output' for item in inputs):
            return text_payload('finished')
        time.sleep(1.2)
        return tool_payload(('search_count', {'model': 'res.partner'}))

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_a_request_thread_runs_the_turn_past_the_cron_limit(self):
        user = new_test_user(self.env, login='ai_budget_user', groups='base.group_user')
        sessions = self.env['muk_ai.session'].with_user(user)
        with (
            patch.object(
                type(self.env['muk_ai.provider']),
                '_request_responses',
                autospec=True,
                side_effect=self._answer,
            ),
            patch.object(
                type(self.env['muk_mcp.tool']),
                '_execute',
                autospec=True,
                return_value=('{}', {}, None),
            ),
        ):
            for options, state in (
                ({'limit_time_real_cron': 1}, 'running'),
                ({'limit_time_real_cron': 0, 'limit_time_real': 1}, 'running'),
            ):
                with self.subTest(options=options), patch.dict(config.options, options):
                    session = sessions.create({'name': 'cron thread'})
                    self.assertEqual(session.send_message('go')['state'], state)
            session = sessions.create({'name': 'request thread'})
            self.authenticate(user.login, user.login)
            with patch.dict(config.options, {'limit_time_real_cron': 1}):
                snapshot = self.make_jsonrpc_request(
                    '/web/dataset/call_kw/muk_ai.session/send_message',
                    {
                        'model': 'muk_ai.session',
                        'method': 'send_message',
                        'args': [[session.id], 'go'],
                        'kwargs': {},
                    },
                )
        self.assertEqual(
            (snapshot['state'], snapshot['last_text']), ('done', 'finished')
        )
