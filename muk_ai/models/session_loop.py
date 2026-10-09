from __future__ import annotations

import re
import threading
import time

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import config

from odoo.addons.muk_ai.tools.attachment import INLINE_IMAGE_RE
from odoo.addons.muk_ai.tools.runtime import (
    ITERATION_WARNING_ROUNDS,
    MAX_ITERATIONS,
    MAX_WALLCLOCK_SECONDS,
    TURN_WALLCLOCK_SECONDS,
    WALLCLOCK_MIN_SECONDS,
    WALLCLOCK_SAFETY_MARGIN,
    WORKER_HEARTBEAT_INTERVAL,
    StreamCancelled,
    TurnSuperseded,
)
from odoo.addons.muk_ai.tools.stream import StreamBuffer

STATE_CHECK_SECONDS = 0.3


class AISessionLoop(models.AbstractModel):
    """Turn engine of a chat: provider rounds, streaming, budgets and usage."""

    _name = 'muk_ai.session.loop'
    _description = 'AI Session Turn Engine'
    _explanation = (
        'The part of a chat that runs a turn: it streams the model answer, '
        'counts tokens and cost, and stops at the turn budgets.'
    )

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    turn_seq = fields.Integer(
        string='Turn',
        readonly=True,
        default=0,
        copy=False,
    )

    iteration_count = fields.Integer(
        string='Iterations',
        readonly=True,
        default=0,
    )

    turn_wallclock_spent = fields.Float(
        string='Turn Wallclock Spent',
        readonly=True,
        default=0.0,
        copy=False,
    )

    turn_cost_spent = fields.Float(
        string='Turn Cost Spent',
        readonly=True,
        default=0.0,
        copy=False,
    )

    total_input_tokens = fields.Integer(
        string='Input Tokens',
        readonly=True,
        default=0,
    )

    total_output_tokens = fields.Integer(
        string='Output Tokens',
        readonly=True,
        default=0,
    )

    total_input_cost = fields.Float(
        string='Input Cost (USD)',
        readonly=True,
        default=0.0,
        digits=(12, 6),
    )

    total_output_cost = fields.Float(
        string='Output Cost (USD)',
        readonly=True,
        default=0.0,
        digits=(12, 6),
    )

    total_cost = fields.Float(
        string='Total Cost (USD)',
        help='Cumulative USD for this session (input + output).',
        readonly=True,
        default=0.0,
        digits=(12, 6),
    )

    last_input_tokens = fields.Integer(
        string='Last Input Tokens',
        readonly=True,
        default=0,
    )

    turn_usage = fields.Json(
        string='Turn Usage',
        readonly=True,
        copy=False,
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _int_config_param(self, key: str, default: int) -> int:
        """Return a positive integer config parameter, or the default."""
        value = self.env['ir.config_parameter'].sudo().get_int(key)
        return value if value > 0 else default

    @api.model
    def _max_iterations(self) -> int:
        """Return the configured maximum LLM rounds per worker slice."""
        return self._int_config_param('muk_ai.max_iterations', MAX_ITERATIONS)

    @api.model
    def _worker_hard_limit_seconds(self) -> int:
        """Return the real-time budget of the current worker context.

        A request thread of the threaded server runs without a time limit.

        :return: the configured cron limit, or ``0`` when no limit applies
        """
        if getattr(threading.current_thread(), 'processing_http', False):
            return 0
        limit = config['limit_time_real_cron']
        if not limit or limit < 0:
            limit = config['limit_time_real'] or 0
        return max(limit, 0)

    @api.model
    def _slice_wallclock_seconds(self) -> int:
        """Return the per-slice wallclock budget capped by the worker limit."""
        configured = self._int_config_param(
            'muk_ai.slice_wallclock_seconds', MAX_WALLCLOCK_SECONDS
        )
        if hard := self._worker_hard_limit_seconds():
            budget = max(WALLCLOCK_MIN_SECONDS, hard - WALLCLOCK_SAFETY_MARGIN)
            return min(configured, budget, hard)
        return configured

    @api.model
    def _turn_wallclock_seconds(self) -> int:
        """Return the configured total wallclock budget for a user turn."""
        return self._int_config_param(
            'muk_ai.turn_wallclock_seconds', TURN_WALLCLOCK_SECONDS
        )

    @api.model
    def _turn_cost_limit(self) -> float:
        """Return the configured per-turn cost limit, or ``0.0`` when unset."""
        params = self.env['ir.config_parameter'].sudo()
        return max(params.get_float('muk_ai.turn_cost_limit'), 0.0)

    def _turn_start_values(self) -> dict:
        """Return the values that put the session into a fresh turn.

        They clear the turn budgets and advance ``turn_seq``, against which a
        streaming worker detects a superseded turn.
        """
        return {
            'state': 'running',
            'error_message': False,
            'claimed_at': False,
            'turn_seq': (self.turn_seq or 0) + 1,
            'turn_wallclock_spent': 0.0,
            'turn_cost_spent': 0.0,
            'turn_usage': False,
        }

    def _publish_now(self, event_type: str, payload: dict) -> None:
        """Publish a streamed event and commit, so the client sees it at once."""
        self._publish_event(event_type, payload)
        self._commit_safe()

    def _check_cancelled(self, stream: StreamBuffer) -> None:
        """Poll the session while it streams, keeping its worker claim fresh.

        :raise StreamCancelled: when the session was stopped, its partial
            answer kept
        :raise TurnSuperseded: when a newer turn replaced the one streamed
        """
        if (now := time.monotonic()) - stream.checked < STATE_CHECK_SECONDS:
            return
        stream.checked = now
        self.invalidate_recordset(['state', 'turn_seq'])
        if self.state == 'stopped':
            if stream.text:
                self._persist_partial(stream.text)
                stream.text = ''
                self._commit_safe()
            raise StreamCancelled()
        if stream.turn is not None and stream.turn != self.turn_seq:
            stream.pending.clear()
            raise TurnSuperseded()
        if now - stream.beat >= WORKER_HEARTBEAT_INTERVAL:
            stream.beat = now
            self.claimed_at = fields.Datetime.now()
            self._commit_safe()

    def _on_stream_delta(self, kind: str, payload: dict, stream: StreamBuffer) -> None:
        """Coalesce and publish a streamed delta of the given kind."""
        self._check_cancelled(stream)
        delta = payload.get('delta') or ''
        if kind == 'text' and delta:
            stream.text += delta
            stream.add('text_delta', delta)
        elif kind == 'reasoning' and delta:
            stream.add('reasoning_delta', delta)
        elif kind == 'tool_start':
            stream.flush('text_delta')
            self._publish_now(
                'tool_call_start',
                {'call_id': payload.get('call_id'), 'name': payload.get('name')},
            )
        elif kind == 'tool_args' and delta and payload.get('call_id'):
            stream.add('tool_call_args_delta', delta, call_id=payload['call_id'])

    def _persist_partial(self, text: str) -> None:
        """Keep the answer streamed so far as an assistant message."""
        message = {
            'type': 'message',
            'role': 'assistant',
            'content': [{'type': 'output_text', 'text': text}],
        }
        self.write(
            {'last_text': text, 'conversation': [*(self.conversation or []), message]}
        )
        self._append_event({'kind': 'text', 'content': text})
        self.flush_recordset()

    def _stream_provider_round(
        self,
        provider: models.BaseModel,
        tool_schema: list,
        model: str | None,
        agent: models.BaseModel,
        cache: dict | None = None,
        notice: dict | None = None,
    ) -> dict:
        """Run one streaming provider round, flushing the buffered deltas after it.

        :param agent: the agent whose built-in tools the round serves, if any
        :raise StreamCancelled: when the session is cancelled mid-stream
        """
        stream = StreamBuffer(self._publish_now, self.turn_seq)
        inputs = self._build_request_inputs()
        try:
            return provider._request_responses(
                inputs=[*inputs, notice] if notice else inputs,
                tools_schema=tool_schema,
                model=model,
                on_delta=lambda kind, data: self._on_stream_delta(kind, data, stream),
                reasoning_effort=self._effective_reasoning_effort(),
                enable_web_search=bool(agent) and self._web_search_route() == 'native',
                enable_code_interpreter=bool(agent)
                and self._code_interpreter_route() == 'native',
                cache_key=f'muk_ai.session:{self.id}',
                cache=cache,
            )
        finally:
            stream.flush()

    def _accrue_usage(
        self, usage: dict | None, record: models.BaseModel | None = None
    ) -> None:
        """Charge a usage payload to the session's ledger.

        Without ``record`` the usage is a round of the chat model: it counts as
        an iteration with its tokens. A ``record`` prices a cost of its own.
        """
        usage = usage or {}
        turn = dict(self.turn_usage or {})
        values = {}
        if record is None:
            record = self._resolve_model_for('chat')
            input_tokens = usage.get('input_tokens')
            output_tokens = usage.get('output_tokens', 0)
            values = {
                'iteration_count': self.iteration_count + 1,
                'total_input_tokens': self.total_input_tokens + (input_tokens or 0),
                'total_output_tokens': self.total_output_tokens + output_tokens,
                'last_input_tokens': (
                    self.last_input_tokens if input_tokens is None else input_tokens
                ),
            }
            turn.update(
                input_tokens=turn.get('input_tokens', 0) + (input_tokens or 0),
                output_tokens=turn.get('output_tokens', 0) + output_tokens,
                iterations=turn.get('iterations', 0) + 1,
            )
        if record:
            cost = record._compute_usage_cost(usage)
            turn['cost'] = turn.get('cost', 0.0) + cost['total_cost']
            values.update(
                total_input_cost=self.total_input_cost + cost['input_cost'],
                total_output_cost=self.total_output_cost + cost['output_cost'],
                total_cost=self.total_cost + cost['total_cost'],
                turn_cost_spent=self.turn_cost_spent + cost['total_cost'],
            )
        self.write({**values, 'turn_usage': turn})

    def _persist_inline_images(self, text: str, cache: dict) -> str:
        """Store the base64 images inlined in a text and link them instead.

        :param cache: attachment ids of the images stored this round, by data
        """

        def store(match: re.Match) -> str:
            """Store one inline image and return the reference replacing it."""
            alt, mimetype = match.group(1) or 'generated.png', match.group(2)
            data = re.sub(r'\s+', '', match.group(3))
            if data not in cache:
                try:
                    cache[data] = (
                        self.env['ir.attachment']
                        .sudo()
                        ._ai_create_from_upload(alt, mimetype, data, res_id=self.id)
                        .id
                    )
                except UserError:
                    return match.group(0)
            return (
                f'![{alt}](/web/image/{cache[data]}) _(attachment {cache[data]} - '
                f'to set on a record use `image_1920="@attachment:{cache[data]}"`)_'
            )

        return INLINE_IMAGE_RE.sub(store, text)

    def _accrue_round_payload(self, payload: dict) -> None:
        """Accrue usage and persist the text and carried inputs of a round.

        Images inlined as base64 are stored once and linked in both.
        """
        self._accrue_usage(payload.get('usage'))
        cache = {}
        if text := self._persist_inline_images(payload.get('text') or '', cache):
            payload['text'] = self.last_text = text
            self._append_event({'kind': 'text', 'content': text})
        self._extend_conversation(
            [
                {
                    **item,
                    'content': [
                        {
                            **block,
                            'text': self._persist_inline_images(block['text'], cache),
                        }
                        if isinstance(block, dict)
                        and isinstance(block.get('text'), str)
                        else block
                        for block in item['content']
                    ],
                }
                if isinstance(item, dict) and isinstance(item.get('content'), list)
                else item
                for item in payload.get('carry_inputs') or []
            ]
        )

    def _turn_budget_error(self, turn_budget: float) -> None:
        """Transition to error when the turn wallclock budget is exhausted."""
        self._transition_state(
            'error',
            error=self.env._(
                'Turn wallclock budget reached (%(s)s s). Send a new message to continue.',
                s=int(turn_budget),
            ),
        )

    def _max_iterations_error(self) -> None:
        """Transition to error when the turn ran out of iterations."""
        self._transition_state('error', error=self.env._('Maximum iterations reached.'))

    def _turn_cost_error(self, limit: float) -> None:
        """Transition to error when the turn cost budget is reached."""
        self._transition_state(
            'error',
            error=self.env._(
                'Turn cost budget reached (%(amount).2f %(currency)s). '
                'Send a new message to continue.',
                amount=limit,
                currency=self._resolve_model_for('chat').currency or 'USD',
            ),
        )

    def _round_limit_notice(self, remaining: int | None) -> dict | None:
        """Build a user-visible notice about remaining round and cost budget."""
        parts = []
        if remaining is not None:
            parts.append(f'Only {remaining} tool round(s) remain for this turn.')
        if (limit := self._turn_cost_limit()) and (
            spent := self.turn_cost_spent or 0.0
        ) >= 0.8 * limit:
            currency = self._resolve_model_for('chat').currency or 'USD'
            parts.append(
                f'Only {max(limit - spent, 0.0):.2f} {currency} of the '
                f'{limit:.2f} {currency} turn cost budget remain.'
            )
        if not parts:
            return None
        parts.append('Finish the task now or summarize progress and next steps.')
        return {
            'role': 'user',
            'content': [
                {
                    'type': 'input_text',
                    'text': f'<turn_limits>{" ".join(parts)}</turn_limits>',
                }
            ],
            '_cache_volatile': True,
        }

    def _run_to_completion(self, has_terminating: bool = False) -> None:
        """Drive the turn across iterations and slices until it settles."""
        slice_start = time.monotonic()
        spent_before = self.turn_wallclock_spent or 0.0
        turn_budget = self._turn_wallclock_seconds()
        if spent_before >= turn_budget:
            self._turn_budget_error(turn_budget)
            return
        deadline = slice_start + min(
            self._slice_wallclock_seconds(), turn_budget - spent_before
        )
        while True:
            self._maybe_auto_compact()
            if self.state != 'running':
                return
            self._run_iterations(deadline, has_terminating=has_terminating)
            if self.state == 'running' and time.monotonic() > deadline:
                spent = min(spent_before, self.turn_wallclock_spent or 0.0)
                spent += time.monotonic() - slice_start
                self.write({'turn_wallclock_spent': spent})
                if spent >= turn_budget:
                    self._turn_budget_error(turn_budget)
                else:
                    self._yield_slice()
                return
            if self.state != 'done' or not self._drain_pending_message():
                return
            if time.monotonic() > deadline:
                self._yield_slice()
                return
            self._transition_state('running')
            has_terminating = False

    def _run_iterations(self, deadline: float, has_terminating: bool = False) -> None:
        """Run provider rounds until completion, deadline, or budget limits."""
        cache = {}
        max_iterations = self._max_iterations()
        for iteration in range(max_iterations):
            if self.state != 'running' or time.monotonic() > deadline:
                return
            self._maybe_auto_compact()
            if self.state != 'running':
                return
            if (limit := self._turn_cost_limit()) and (
                self.turn_cost_spent or 0.0
            ) >= limit:
                self._turn_cost_error(limit)
                return
            self.invalidate_recordset(['pending_ids', 'expanded_tool_names'])
            if self.pending_ids and self._drain_pending_message():
                has_terminating = False
            remaining = max_iterations - iteration
            try:
                payload = self._stream_provider_round(
                    self._resolve_provider(),
                    None if has_terminating else self._get_tool_schema(),
                    self._effective_model(),
                    None if has_terminating else self.agent_id,
                    cache=cache,
                    notice=self._round_limit_notice(
                        remaining if remaining <= ITERATION_WARNING_ROUNDS else None
                    ),
                )
            except TurnSuperseded:
                raise
            except StreamCancelled:
                if self.state == 'running':
                    self._yield_slice()
                return
            except UserError as error:
                self._transition_state('error', error=str(error))
                return
            self._accrue_round_payload(payload)
            if not (tool_calls := payload.get('tool_calls')):
                if payload.get('text'):
                    self._transition_state('done')
                else:
                    self._transition_state(
                        'error', error=self.env._('AI returned no output.')
                    )
                return
            result = self._process_tool_round(
                tool_calls, [], 0, has_terminating=has_terminating
            )
            if result is None:
                return
            has_terminating = has_terminating or result
        if self.state == 'running':
            self._max_iterations_error()

    def _serialize_pending(self) -> list[dict]:
        """Return the queued messages, which belong to the owner alone.

        Anyone but the owner and the superuser gets an empty list, whatever
        the record rules grant.
        """
        if not self.env.su and self.user_id != self.env.user:
            return []
        return [pending._to_payload() for pending in self.pending_ids]

    def _enqueue_user_turn(
        self,
        user_message: str | None,
        attachments: models.BaseModel,
        extend: bool = True,
    ) -> None:
        """Start a running turn from a user message and attachments."""
        if extend and (entry := self._build_user_entry(user_message, attachments)):
            self._extend_conversation([entry])
        if user_message or attachments:
            self._append_event(self._user_message_log(user_message, attachments))
        self._transition_state('running', values=self._turn_start_values())

    def _drain_pending_message(self) -> bool:
        """Merge queued messages into a new turn; return whether any drained."""
        if not (pending := self.pending_ids):
            return False
        message = '\n\n'.join(p.content for p in pending if (p.content or '').strip())
        attachments = self._resolve_attachments(
            [aid for p in pending for aid in p.attachment_ids or []]
        )
        pending.unlink()
        self.invalidate_recordset(['pending_ids'])
        self._publish_event('queue', {'pending': []})
        self._enqueue_user_turn(message, attachments)
        return True
