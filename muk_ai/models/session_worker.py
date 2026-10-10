from __future__ import annotations

import contextlib
import json
import random
from collections.abc import Iterator
from datetime import timedelta

import psycopg2

from odoo import SUPERUSER_ID, api, fields, models, modules
from odoo.exceptions import UserError
from odoo.fields import Domain
from odoo.http import request
from odoo.tools import SQL, config

from odoo.addons.muk_ai.tools.runtime import (
    CLIENT_ACTION_TIMEOUT_SECONDS,
    DISPATCH_MAX_TURNS,
    GC_SESSION_BATCH,
    WORKER_STALE_THRESHOLD,
    StreamCancelled,
    TurnSuperseded,
    advisory_unlock,
    commit_safe,
    try_advisory_lock,
    vacuum,
)


class AISessionWorker(models.AbstractModel):
    """Worker side of a chat: dispatch, advisory locks, sweeps and retention."""

    _name = 'muk_ai.session.worker'
    _description = 'AI Session Worker'
    _explanation = (
        'The part of a chat that hands its turns to a worker, keeps two '
        'workers off the same chat and cleans up what they left behind.'
    )

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    claimed_at = fields.Datetime(
        string='Worker Claimed At',
        readonly=True,
        index=True,
        copy=False,
    )

    user_context = fields.Json(
        string='User Context',
        readonly=True,
        copy=False,
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _commit_safe(self) -> None:
        """Commit outside tests, re-raising on serialization conflicts."""
        commit_safe(self.env)

    @contextlib.contextmanager
    def _read_committed(self) -> Iterator[models.BaseModel]:
        """Yield the session in a transaction of its own that reads committed rows.

        A row lock taken there waits for a busy worker's commit instead of
        failing on it. A test runs in its own transaction instead.
        """
        if modules.module.current_test:
            yield self
            return
        with self.env.registry.cursor() as cr:
            cr.execute(SQL('SET TRANSACTION ISOLATION LEVEL READ COMMITTED'))
            yield self.with_env(self.env(cr=cr))

    @contextlib.contextmanager
    def _session_lock(self) -> Iterator[None]:
        """Hold the advisory lock of the session for the duration of a call.

        :raise UserError: when a worker or another call holds it
        """
        if not try_advisory_lock(self.env.cr, self.id):
            raise UserError(
                self.env._('The session is currently busy. Please try again.')
            )
        try:
            yield
        finally:
            advisory_unlock(self.env.cr, self.id)

    def _fail(self, message: str, reason: str | None = None) -> None:
        """Close the tool calls left open and put the session in error.

        :param reason: what the closed calls report, the message by default
        """
        self._close_orphan_tool_calls(
            {'error': 'interrupted', 'reason': reason or message}
        )
        self._transition_state('error', error=message)

    def _recover_if_stuck(self) -> bool:
        """Mark a stalled running session as errored when idle too long."""
        if self.state in ('running', 'compacting') and (
            reference := self.claimed_at or self.write_date
        ):
            idle = (fields.Datetime.now() - reference).total_seconds()
            if idle >= WORKER_STALE_THRESHOLD and try_advisory_lock(
                self.env.cr, self.id, xact=True
            ):
                self._fail(
                    self.env._(
                        'Previous turn timed out after %(idle)s seconds with no activity.',
                        idle=int(idle),
                    ),
                    'previous turn timed out',
                )
                return True
        return False

    def _heartbeat_claim(self) -> None:
        """Refresh the worker claim timestamp and commit safely."""
        self.sudo().write({'claimed_at': fields.Datetime.now()})
        self._commit_safe()

    @api.model
    def _rate_limit_domain(self) -> list:
        """Return the domain counting the chats this user started this minute."""
        return [
            ('user_id', '=', self.env.user.id),
            ('create_date', '>=', fields.Datetime.now() - timedelta(minutes=1)),
        ]

    @api.model
    def _check_rate_limit(self, batch_size: int = 1) -> None:
        """Raise when creating ``batch_size`` sessions exceeds the rate limit.

        The limit is the one of the default provider.

        :raise UserError: when the per-minute rate limit would be exceeded
        """
        if limit := max(self.env['muk_ai.provider']._get_default().rate_limit, 0):
            count = self.sudo().search_count(self._rate_limit_domain())
            if count + batch_size > limit:
                raise UserError(
                    self.env._(
                        'Rate limit reached: the limit for new chats is '
                        '%(limit)s per minute. You started %(count)s in the '
                        'last minute and asked for %(batch)s more. Try again '
                        'in a minute.',
                        limit=limit,
                        count=count,
                        batch=batch_size,
                    )
                )

    @api.model
    def _session_worker_crons(self) -> models.BaseModel:
        """Return the active AI-session worker cron records."""
        return (
            self.env['ir.cron']
            .sudo()
            .search([('state', '=', 'ai_session'), ('active', '=', True)])
        )

    def _wake_worker_cron(self) -> None:
        """Ask one of the worker crons to pick the session up."""
        if crons := self._session_worker_crons():
            random.choice(crons)._trigger()

    def _yield_slice(self) -> None:
        """Commit and let a worker cron continue the turn elsewhere."""
        if modules.module.current_test:
            return
        self._commit_safe()
        self._wake_worker_cron()

    @api.model
    def _dispatch_inline(self) -> bool:
        """Return whether a queued turn may run in the current request.

        It may outside tests on a server without worker processes, unless
        the ``muk_ai.dispatch_mode`` parameter is ``cron``.
        """
        if modules.module.current_test or config['workers']:
            return False
        params = self.env['ir.config_parameter'].sudo()
        return params.get_str('muk_ai.dispatch_mode') != 'cron'

    def _trigger_worker(self) -> None:
        """Persist the user context and dispatch the turn to a worker.

        A test runs the turn right away instead.
        """
        context = {}
        for key, value in self.env.context.items():
            try:
                json.dumps(value)
            except (TypeError, ValueError):
                continue
            context[key] = value
        self.sudo().write({'user_context': context})
        if modules.module.current_test:
            for session in self:
                if session.state == 'compacting':
                    session._do_compact()
                elif session.state == 'running':
                    session._run_to_completion()
            return
        self._wake_worker_cron()
        if request and self._dispatch_inline():
            queued = getattr(request, 'muk_ai_dispatch_ids', ())
            request.muk_ai_dispatch_ids = tuple(dict.fromkeys(queued + tuple(self.ids)))

    @api.model
    def _dispatch_in_slot(self, session_ids: tuple[int, ...]) -> None:
        """Run the queued turns while holding one of the shared dispatch slots.

        Slots are keyed negatively, apart from the per-session locks.

        :param session_ids: sessions to hand to the worker, in queue order
        """
        cr = self.env.cr
        slots = range(-1, -DISPATCH_MAX_TURNS - 1, -1)
        if (slot := next((s for s in slots if try_advisory_lock(cr, s)), None)) is None:
            return
        try:
            for session_id in session_ids:
                self._process_session_in_worker(session_id)
        finally:
            advisory_unlock(cr, slot)

    @api.model
    def _find_pending_session_ids(self, limit: int | None = None) -> list[int]:
        """Return ids of pending sessions, oldest first, one per worker by default."""
        return (
            self.sudo()
            .search(
                [('state', 'in', ('running', 'compacting'))],
                order='write_date',
                limit=limit or max(1, len(self._session_worker_crons())),
            )
            .ids
        )

    @api.model
    def _process_session_in_worker(self, session_id: int) -> bool:
        """Process one session under its advisory lock in a fresh cursor.

        A turn superseded mid-stream wakes another worker once the lock is
        released.
        """
        processed = superseded = False
        with self.pool.cursor() as cr:
            if not try_advisory_lock(cr, session_id):
                return False
            try:
                owner = api.Environment(cr, SUPERUSER_ID, {})['muk_ai.session']
                owner = owner.browse(session_id).exists()
                if owner.state in ('running', 'compacting'):
                    env = api.Environment(
                        cr, owner.user_id.id, owner.user_context or {}
                    )
                    session = env['muk_ai.session'].browse(session_id)
                    session.write({'claimed_at': fields.Datetime.now()})
                    cr.commit()
                    try:
                        if session.state == 'compacting':
                            session._do_compact()
                        else:
                            session._run_to_completion()
                        cr.commit()
                    except TurnSuperseded:
                        cr.rollback()
                        superseded = True
                    except StreamCancelled:
                        cr.rollback()
                    except Exception as error:
                        cr.rollback()
                        self._mark_session_error(session_id, str(error))
                    processed = True
            finally:
                advisory_unlock(cr, session_id)
        if superseded:
            self.browse(session_id)._wake_worker_cron()
        return processed

    @api.model
    def _mark_session_error(self, session_id: int, message: str) -> None:
        """Mark a session errored in its own cursor and notify the client."""
        with self.pool.cursor() as cr:
            session = api.Environment(cr, SUPERUSER_ID, {})['muk_ai.session']
            if session := session.browse(session_id).exists():
                session._fail(message)
                cr.commit()

    @api.model
    def _retention_days(self) -> int:
        """Return the days a finished chat is kept, zero to keep it forever."""
        params = self.env['ir.config_parameter'].sudo()
        if not params.get_bool('muk_ai.session_retention_enabled'):
            return 0
        return max(params.get_int('muk_ai.session_retention_days'), 0)

    @api.model
    def _gc_sessions_older_than(self, days: int, domain: Domain) -> tuple[int, int]:
        """Delete one batch of the finished chats matching ``domain`` past ``days``.

        :param days: how long such a chat is kept, zero to keep it forever
        :return: how many chats were deleted, and how many are still due
        """
        if days <= 0:
            return 0, 0
        cutoff = fields.Datetime.now() - timedelta(days=days)
        stale = domain & Domain(
            [
                ('state', 'in', ('done', 'error', 'stopped')),
                ('write_date', '<', cutoff),
            ]
        )
        return vacuum(self.sudo(), stale, GC_SESSION_BATCH)

    # ----------------------------------------------------------
    # Cron
    # ----------------------------------------------------------

    @api.model
    def _sweep_stale_client_actions(self) -> None:
        """Auto-reject client-action batches whose client never responded."""
        params = self.env['ir.config_parameter'].sudo()
        timeout = params.get_int(
            'muk_ai.client_action_timeout', CLIENT_ACTION_TIMEOUT_SECONDS
        )
        if timeout <= 0:
            return
        threshold = fields.Datetime.now() - timedelta(seconds=timeout)
        for session in self.sudo().search([('state', '=', 'waiting')]):
            pending = session.pending_ask or {}
            registered = fields.Datetime.to_datetime(pending.get('registered_at'))
            if (
                pending.get('kind') == 'client_action'
                and registered
                and (registered <= threshold)
            ):
                with contextlib.suppress(UserError):
                    session.reject_client_action(
                        reason='timeout: the client did not respond'
                    )

    @api.model
    def _sweep_orphan_sessions(self, skip_ids: list[int] | None = None) -> None:
        """Mark abandoned running or compacting sessions as errored."""
        threshold = fields.Datetime.now() - timedelta(seconds=WORKER_STALE_THRESHOLD)
        for session in self.sudo().search(
            [
                ('id', 'not in', skip_ids or []),
                ('state', 'in', ('running', 'compacting')),
                ('write_date', '<', threshold),
                '|',
                ('claimed_at', '=', False),
                ('claimed_at', '<', threshold),
            ]
        ):
            if not try_advisory_lock(self.env.cr, session.id, xact=True):
                continue
            with (
                contextlib.suppress(psycopg2.errors.SerializationFailure),
                self.env.cr.savepoint(),
            ):
                session._fail(
                    self.env._('Worker abandoned the session - please retry.'),
                    'worker abandoned the session',
                )

    @api.model
    def _cron_run_pending_sessions(self) -> None:
        """Sweep orphans and process pending sessions in this worker slot."""
        candidates = self._find_pending_session_ids()
        self._sweep_orphan_sessions(skip_ids=candidates)
        self._sweep_stale_client_actions()
        if candidates:
            self._commit_safe()
            for session_id in candidates:
                if self._process_session_in_worker(session_id):
                    break
            if len(candidates) > 1:
                self._wake_worker_cron()
