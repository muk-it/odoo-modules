from __future__ import annotations

import json

from odoo import SUPERUSER_ID, api, fields, models
from odoo.exceptions import UserError
from odoo.osv import expression
from odoo.tools import html2plaintext

from odoo.addons.muk_ai_schedule.tools.constants import (
    MESSAGE_PREVIEW_CHARS,
    WAIT_TOOL,
    WAKE_RESET,
)


class AISession(models.Model):
    """Let a chat pause itself with the wait tool and carry on when woken."""

    _inherit = 'muk_ai.session'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    wake_at = fields.Datetime(
        string='Wakes At',
        help='When a waiting chat carries on at the latest.',
        readonly=True,
        index=True,
        copy=False,
    )

    wake_res_model = fields.Char(
        string='Watched Model',
        help='The model of the record a waiting chat watches.',
        readonly=True,
        copy=False,
    )

    wake_res_id = fields.Many2oneReference(
        model_field='wake_res_model',
        string='Watched Record',
        help='The record a waiting chat watches.',
        readonly=True,
        index='btree_not_null',
        copy=False,
    )

    wake_count = fields.Integer(
        string='Waits',
        help='How many times the chat paused itself to wait.',
        readonly=True,
        copy=False,
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _waits_for_wakeup(self) -> bool:
        """Return whether the chat is paused by the wait tool."""
        return (
            self.state == 'waiting' and (self.pending_ask or {}).get('kind') == 'wakeup'
        )

    def _wait_for(self, plan: dict, paused: dict) -> None:
        """Pause the round of a wait call until the plan of the tool wakes the chat."""
        record = plan['record'] or {}
        pending = {'kind': 'wakeup', **paused, **plan}
        self.write(
            {
                'state': 'waiting',
                'wake_at': plan['resume_at'],
                'wake_res_model': record.get('model') or False,
                'wake_res_id': record.get('id') or False,
                'wake_count': self.wake_count + 1,
                'pending_ask': pending,
            }
        )
        self._publish_event(
            'state', {'state': 'waiting', 'ask': self._public_pending_ask(pending)}
        )
        self.env.ref('muk_ai_schedule.cron_wake_sessions')._trigger(self.wake_at)

    def _wake_reason(self) -> str | None:
        """Return why the waiting chat wakes up now, ``None`` while it keeps waiting.

        A condition is checked with the rights of the chat's owner.
        """
        pending = self.pending_ask or {}
        if pending.get('message'):
            return 'message'
        if self.wake_res_model:
            if (
                self.wake_res_model not in self.env
                or not self.env[self.wake_res_model].browse(self.wake_res_id).exists()
            ):
                return 'record_deleted'
            if condition := pending.get('condition'):
                watched = self.env[self.wake_res_model].with_user(self.user_id)
                try:
                    if watched.search_count(
                        expression.AND([[('id', '=', self.wake_res_id)], condition]),
                        limit=1,
                    ):
                        return 'condition_met'
                except ValueError:
                    return 'condition_invalid'
        if self.wake_at <= fields.Datetime.now():
            return 'timeout' if self.wake_res_model else 'time'
        return None

    def _wake(self, reason: str) -> None:
        """Answer the paused wait call with why the chat woke and carry on with the round.

        A chat that waits without a paused call takes its note as the next message.
        The caller starts the worker once its own changes are in.
        """
        pending = dict(self.pending_ask or {})
        result = {
            'status': 'woken',
            'reason': reason,
            'woken_at': fields.Datetime.to_string(fields.Datetime.now()),
            'note': pending.get('note'),
        }
        if message := pending.get('message'):
            result['message'] = message
        if not pending.get('call_id'):
            self.pending_ask = False
            self._enqueue_user_turn(pending.get('note'), self.env['ir.attachment'])
            return
        outputs = list(pending['outputs'])
        self._record_tool_result(
            outputs,
            pending['call_id'],
            pending['name'],
            result,
            arguments=pending['arguments'],
        )
        self.write(
            {
                'pending_ask': False,
                'claimed_at': False,
                'turn_wallclock_spent': 0.0,
                'turn_cost_spent': 0.0,
            }
        )
        self._transition_state('running')
        self._process_tool_round(
            list(pending['tool_calls']),
            outputs,
            pending['resume_index'] + 1,
            has_terminating=bool(pending['has_terminating']),
        )

    @api.model
    def _wake_in_worker(self, session_id: int, reason: str) -> None:
        """Wake one chat as its owner, under its advisory lock, in a fresh cursor."""
        with self.pool.cursor() as cr:
            sessions = api.Environment(cr, SUPERUSER_ID, {})['muk_ai.session']
            if not sessions._try_session_lock(session_id):
                return
            try:
                owner = sessions.browse(session_id).exists()
                if not owner._waits_for_wakeup():
                    return
                env = api.Environment(cr, owner.user_id.id, owner.user_context or {})
                try:
                    session = env['muk_ai.session'].browse(session_id)
                    session._wake(reason)
                    session._trigger_worker()
                    cr.commit()
                except Exception as error:
                    cr.rollback()
                    self._mark_session_error(session_id, str(error))
            finally:
                sessions._release_session_lock(session_id)

    @api.model
    def _wake_on_message(self, message: models.BaseModel) -> None:
        """Wake the chats waiting for a message on the record it was posted on."""
        sessions = (
            self.sudo()
            .search(
                [
                    ('state', '=', 'waiting'),
                    ('wake_res_model', '=', message.model),
                    ('wake_res_id', '=', message.res_id),
                ]
            )
            .filtered(lambda session: (session.pending_ask or {}).get('on_message'))
        )
        for session in sessions:
            session.pending_ask = {
                **session.pending_ask,
                'message': {
                    'id': message.id,
                    'author': message.author_id.display_name
                    or message.email_from
                    or '',
                    'date': fields.Datetime.to_string(message.date),
                    'subject': message.subject or '',
                    'body': html2plaintext(message.body or '')[:MESSAGE_PREVIEW_CHARS],
                },
            }
        if sessions:
            self.env.ref('muk_ai_schedule.cron_wake_sessions')._trigger()

    @api.model
    def _eager_tool_name_registry(self) -> set[str]:
        """Add the wait tool to the tools a chat may load upfront."""
        return super()._eager_tool_name_registry() | {WAIT_TOOL}

    def _eager_tool_names(self) -> set[str]:
        """Load the wait tool upfront in every chat."""
        return super()._eager_tool_names() | {WAIT_TOOL}

    def _execute_tool_call(
        self,
        call: dict,
        tool_calls: list,
        outputs: list,
        index: int,
        has_terminating: bool,
    ) -> bool | None:
        """Pause the round on a wait call until the chat is woken."""
        if call['name'] != WAIT_TOOL:
            return super()._execute_tool_call(
                call, tool_calls, outputs, index, has_terminating
            )
        self._record_tool_call(call)
        result, ok = self.with_context(
            muk_ai_wait_call_id=call['call_id']
        )._dispatch_tool_call(call['name'], call['arguments'], call['call_id'])
        plan = json.loads(result) if ok and isinstance(result, str) else {}
        if plan.get('status') == 'waiting':
            self._wait_for(
                plan,
                {
                    'call_id': call['call_id'],
                    'name': call['name'],
                    'arguments': call['arguments'],
                    'tool_calls': tool_calls,
                    'outputs': outputs,
                    'resume_index': index,
                    'has_terminating': has_terminating,
                },
            )
            return None
        self._record_tool_result(
            outputs, call['call_id'], call['name'], result, arguments=call['arguments']
        )
        return False

    def _notify_state_transition(self, payload: dict) -> None:
        """Keep a chat that waits for its wake-up out of the owner's inbox."""
        if not (
            payload.get('state') == 'waiting'
            and (payload.get('ask') or {}).get('kind') == 'wakeup'
        ):
            super()._notify_state_transition(payload)

    # ----------------------------------------------------------
    # Actions
    # ----------------------------------------------------------

    def action_wake_now(self) -> dict:
        """Wake the waiting chat at once and return its snapshot.

        :raise AccessError: when the caller may only read the chat
        :raise UserError: when the chat does not wait for a wake-up or is busy
        """
        self.check_access('write')
        if not self._waits_for_wakeup():
            raise UserError(self.env._('This chat is not waiting.'))
        if not self._try_session_lock(self.id):
            raise UserError(
                self.env._('The session is currently busy. Please try again.')
            )
        try:
            self._wake('manual')
            self._trigger_worker()
        finally:
            self._release_session_lock(self.id)
        return self.get_snapshot()

    def send_message(
        self, user_message: str, attachment_ids: list[int] | None = None
    ) -> dict:
        """Wake a waiting chat and hand it the message as the next turn.

        :raise UserError: when the chat is busy
        """
        if not self._waits_for_wakeup():
            return super().send_message(user_message, attachment_ids=attachment_ids)
        self.check_access('write')
        if not self._try_session_lock(self.id):
            raise UserError(
                self.env._('The session is currently busy. Please try again.')
            )
        try:
            self._wake('user_message')
            self._enqueue_user_turn(
                user_message, self._resolve_attachments(attachment_ids)
            )
            self._trigger_worker()
        finally:
            self._release_session_lock(self.id)
        return self.get_snapshot()

    # ----------------------------------------------------------
    # Compute
    # ----------------------------------------------------------

    @api.depends('state', 'pending_ask')
    def _compute_awaiting_user(self) -> None:
        """Leave a chat that waits for its wake-up out of the chats awaiting the owner."""
        super()._compute_awaiting_user()
        for record in self:
            if record._waits_for_wakeup():
                record.awaiting_user = False

    # ----------------------------------------------------------
    # ORM
    # ----------------------------------------------------------

    def write(self, vals: dict) -> bool:
        """Clear what a chat waits for when it leaves the waiting state."""
        if vals.get('state', 'waiting') != 'waiting':
            vals = {**WAKE_RESET, **vals}
        return super().write(vals)

    # ----------------------------------------------------------
    # Cron
    # ----------------------------------------------------------

    @api.model
    def _cron_wake_sessions(self) -> None:
        """Wake every waiting chat whose time came or whose record is ready."""
        waiting = self.sudo().search(
            [('state', '=', 'waiting'), ('wake_at', '!=', False)], order='wake_at'
        )
        for session in waiting:
            if reason := session._wake_reason():
                self._wake_in_worker(session.id, reason)
