from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from unittest.mock import patch

from odoo import models, modules
from odoo.tools import SQL

from odoo.addons.muk_ai.models import ir_http as ir_http_module
from odoo.addons.muk_ai.models import session as session_module
from odoo.addons.muk_ai.tests.common import AITestCommon, FakeRequest
from odoo.addons.muk_ai.tools import ADVISORY_LOCK_NAMESPACE, DISPATCH_MAX_TURNS


class TestTurnDispatch(AITestCommon):
    """Verify how a queued turn is dispatched to a worker."""

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _resolve_inline(
        self, workers: int = 0, cron_threads: int = 0, mode: str = 'auto'
    ) -> bool:
        """Resolve the dispatch mode under a simulated server configuration.

        :param workers: number of prefork HTTP worker processes
        :param cron_threads: number of cron threads the server spawns itself
        :param mode: value stored in the ``muk_ai.dispatch_mode`` parameter
        """
        self.env['ir.config_parameter'].sudo().set_param('muk_ai.dispatch_mode', mode)
        fake_config = {'workers': workers, 'max_cron_threads': cron_threads}
        with (
            patch.object(modules.module, 'current_test', False),
            patch.object(session_module, 'config', fake_config),
        ):
            return self.env['muk_ai.session']._dispatch_inline()

    def _budget(
        self, method: str, thread_type: str | None, elapsed: int, **limits
    ) -> int:
        """Resolve a budget method under a simulated worker thread context.

        :param method: name of the ``muk_ai.session`` budget method to call
        :param thread_type: value of the running thread's ``type`` attribute
        :param elapsed: seconds the thread has already been running
        :param limits: ``limit_time_real`` and ``limit_time_real_cron`` values
        """
        thread = threading.current_thread()
        previous = (
            getattr(thread, 'type', None),
            getattr(thread, 'start_time', None),
        )
        if thread_type:
            thread.type = thread_type
            thread.start_time = time.time() - elapsed
        try:
            with patch.object(session_module, 'config', limits):
                return getattr(self.env['muk_ai.session'], method)()
        finally:
            for name, value in zip(('type', 'start_time'), previous, strict=True):
                if value is None:
                    if hasattr(thread, name):
                        delattr(thread, name)
                else:
                    setattr(thread, name, value)

    def _hard_limit(self, thread_type: str | None, elapsed: int, **limits) -> int:
        """Resolve the worker hard limit for a simulated thread context."""
        return self._budget(
            '_worker_hard_limit_seconds', thread_type, elapsed, **limits
        )

    def _slice_budget(self, thread_type: str | None, elapsed: int, **limits) -> int:
        """Resolve the per-slice wallclock budget for a simulated thread context."""
        return self._budget('_slice_wallclock_seconds', thread_type, elapsed, **limits)

    @contextmanager
    def _hold_every_dispatch_slot(self) -> Iterator[None]:
        """Claim every inline dispatch slot from a separate database backend."""
        cursor = self.env.registry.cursor()
        claimed = []
        try:
            for slot in range(-1, -DISPATCH_MAX_TURNS - 1, -1):
                cursor.execute(
                    SQL(
                        'SELECT pg_try_advisory_lock(%s, %s)',
                        ADVISORY_LOCK_NAMESPACE,
                        slot,
                    )
                )
                if not cursor.fetchone()[0]:
                    msg = f'failed to claim dispatch slot {slot}'
                    raise AssertionError(msg)
                claimed.append(slot)
            yield
        finally:
            for slot in claimed:
                with suppress(Exception):
                    cursor.execute(
                        SQL(
                            'SELECT pg_advisory_unlock(%s, %s)',
                            ADVISORY_LOCK_NAMESPACE,
                            slot,
                        )
                    )
                    cursor.fetchone()
            cursor.close()

    def _trigger(
        self,
        sessions: models.BaseModel,
        request_obj: FakeRequest,
        inline: bool = True,
    ) -> None:
        """Run ``_trigger_worker`` against a simulated request context.

        :param sessions: sessions whose turn is being queued
        :param request_obj: stand-in bound to the session module
        :param inline: whether inline dispatch is enabled
        """
        with (
            patch.object(modules.module, 'current_test', False),
            patch.object(session_module, 'request', request_obj),
            patch.object(
                type(self.env['muk_ai.session']),
                '_session_worker_crons',
                lambda records: records.env['ir.cron'],
            ),
            patch.object(
                type(self.env['muk_ai.session']),
                '_dispatch_inline',
                lambda records: inline,
            ),
        ):
            sessions._trigger_worker()

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_dispatch_stays_on_cron_during_tests(self):
        self.assertFalse(self.env['muk_ai.session']._dispatch_inline())

    def test_auto_starts_inline_without_own_cron_threads(self):
        self.assertTrue(self._resolve_inline(workers=0, cron_threads=0))

    def test_auto_starts_inline_even_with_cron_threads(self):
        self.assertTrue(self._resolve_inline(workers=0, cron_threads=2))

    def test_prefork_never_runs_a_turn_inline(self):
        self.assertFalse(self._resolve_inline(workers=4, cron_threads=0, mode='inline'))

    def test_mode_can_be_forced_to_cron(self):
        self.assertFalse(self._resolve_inline(workers=0, cron_threads=0, mode='cron'))

    def test_http_budget_subtracts_the_elapsed_request_time(self):
        limit = self._hard_limit(
            'http', 40, limit_time_real=120, limit_time_real_cron=-1
        )
        self.assertIn(limit, range(78, 82))

    def test_http_budget_is_unlimited_when_disabled(self):
        self.assertEqual(
            self._hard_limit('http', 10, limit_time_real=0, limit_time_real_cron=300), 0
        )

    def test_cron_budget_is_used_outside_a_request_thread(self):
        self.assertEqual(
            self._hard_limit(None, 0, limit_time_real=120, limit_time_real_cron=300),
            300,
        )

    def test_slice_never_outlives_the_remaining_http_budget(self):
        for elapsed, limit in ((95, 120), (119, 120), (60, 120)):
            remaining = self._hard_limit(
                'http', elapsed, limit_time_real=limit, limit_time_real_cron=-1
            )
            slice_seconds = self._slice_budget(
                'http', elapsed, limit_time_real=limit, limit_time_real_cron=-1
            )
            self.assertLessEqual(slice_seconds, remaining)

    def test_exhausted_http_budget_is_not_treated_as_unlimited(self):
        slice_seconds = self._slice_budget(
            'http', 600, limit_time_real=120, limit_time_real_cron=-1
        )
        self.assertLessEqual(slice_seconds, 1)

    def test_queue_is_skipped_without_a_request(self):
        session = self.env['muk_ai.session'].create({'name': 'no-request'})
        unbound = FakeRequest(bound=False)
        self._trigger(session, unbound)
        self.assertFalse(hasattr(unbound, 'muk_ai_dispatch_ids'))

    def test_queue_collects_sessions_in_order_without_duplicates(self):
        first = self.env['muk_ai.session'].create({'name': 'first'})
        second = self.env['muk_ai.session'].create({'name': 'second'})
        fake_request = FakeRequest()
        self._trigger(first + second, fake_request)
        self._trigger(first, fake_request)
        self.assertEqual(fake_request.muk_ai_dispatch_ids, (first.id, second.id))

    def test_queue_is_skipped_when_dispatch_stays_on_cron(self):
        session = self.env['muk_ai.session'].create({'name': 'cron-only'})
        fake_request = FakeRequest()
        self._trigger(session, fake_request, inline=False)
        self.assertFalse(getattr(fake_request, 'muk_ai_dispatch_ids', ()))

    def test_slot_is_claimed_and_released_on_the_real_cursor(self):
        session_model = self.env['muk_ai.session']
        slot = session_model._claim_dispatch_slot()
        self.assertEqual(slot, -1)
        session_model._release_dispatch_slot(slot)
        self.assertEqual(session_model._claim_dispatch_slot(), -1)
        session_model._release_dispatch_slot(-1)

    def test_dispatch_is_skipped_when_every_slot_is_taken(self):
        session_model = self.env['muk_ai.session']
        with self._hold_every_dispatch_slot():
            self.assertIsNone(session_model._claim_dispatch_slot())
            with patch.object(
                type(session_model), '_dispatch_queued_turns'
            ) as dispatched:
                session_model._dispatch_in_slot((1,))
            dispatched.assert_not_called()
        self.assertEqual(session_model._claim_dispatch_slot(), -1)
        session_model._release_dispatch_slot(-1)

    def test_slot_is_released_even_when_the_turn_raises(self):
        with (
            patch.object(
                type(self.env['muk_ai.session']),
                '_claim_dispatch_slot',
                lambda records: -1,
            ),
            patch.object(
                type(self.env['muk_ai.session']), '_release_dispatch_slot'
            ) as released,
            patch.object(
                type(self.env['muk_ai.session']),
                '_dispatch_queued_turns',
                side_effect=ValueError('boom'),
            ),
            self.assertRaises(ValueError),
        ):
            self.env['muk_ai.session']._dispatch_in_slot((1,))
        released.assert_called_once_with(-1)

    def test_queued_turns_are_dispatched_in_order(self):
        first = self.env['muk_ai.session'].create({'name': 'first'})
        second = self.env['muk_ai.session'].create({'name': 'second'})
        with patch.object(
            type(self.env['muk_ai.session']), '_process_session_in_worker'
        ) as worker:
            self.env['muk_ai.session']._dispatch_queued_turns((first.id, second.id))
        self.assertEqual(
            [call.args[0] for call in worker.call_args_list], [first.id, second.id]
        )

    def test_dispatch_stops_before_starting_on_a_spent_budget(self):
        thread = threading.current_thread()
        thread.type = 'http'
        thread.start_time = time.time() - 119
        try:
            with (
                patch.object(session_module, 'config', {'limit_time_real': 120}),
                patch.object(
                    type(self.env['muk_ai.session']), '_process_session_in_worker'
                ) as locked,
            ):
                ir_http_module.IrHttp._run_queued_turns(self.env.cr.dbname, (1, 2))
            locked.assert_not_called()
        finally:
            del thread.type, thread.start_time

    def test_dispatch_failures_never_escape_the_callback(self):
        with self.assertLogs(ir_http_module.__name__, level='ERROR') as logs:
            with patch.object(
                ir_http_module, 'Registry', side_effect=ValueError('boom')
            ):
                ir_http_module.IrHttp._run_queued_turns('testdb', (1,))
        self.assertEqual(len(logs.output), 1)
        self.assertIn('Inline AI dispatch failed for sessions (1,)', logs.output[0])
        self.assertIn('ValueError: boom', logs.output[0])
