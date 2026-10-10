from __future__ import annotations

import json
from collections.abc import Callable

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Domain
from odoo.service.model import PG_CONCURRENCY_EXCEPTIONS_TO_RETRY
from odoo.tools import SQL

from odoo.addons.muk_ai.tools.runtime import WALLCLOCK_MIN_SECONDS
from odoo.addons.muk_ai_subagents.tools.constants import (
    ACTIVITY_ARGS_MAX_CHARS,
    CHILD_COLORS,
    DELEGATE_TOOL,
    LEAD_TOOLS,
    LOCK_ATTEMPTS,
    LOOP_HALT_REPEATS,
    LOOP_NOTICE_REPEATS,
    LOOP_WINDOW,
    MESSAGE_TOOL,
    REPORT_PREVIEW_CHARS,
    STATUS_TEXT_CHARS,
    STOP_REASONS,
    SUBAGENT_RULES,
    TERMINAL_STATES,
    loop_notice,
    render_brief,
    report_notice,
    tool_fingerprint,
)


class AISession(models.Model):
    """Run focused subagent chats on behalf of a parent chat and report back."""

    _inherit = 'muk_ai.session'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    parent_session_id = fields.Many2one(
        comodel_name='muk_ai.session',
        string='Parent Chat',
        help='The chat whose delegate call started this subagent.',
        readonly=True,
        index=True,
        copy=False,
        ondelete='cascade',
    )

    delegation_brief = fields.Json(
        string='Delegation Brief',
        help='The task the parent handed over, with the colour and call it belongs to.',
        readonly=True,
        copy=False,
    )

    stop_reason = fields.Selection(
        selection=STOP_REASONS,
        string='Stop Reason',
        help='Why the subagent ended.',
        readonly=True,
        copy=False,
    )

    loop_state = fields.Json(
        string='Loop State',
        help='The recent tool calls of the subagent, to tell when it repeats itself.',
        readonly=True,
        copy=False,
    )

    child_session_ids = fields.One2many(
        comodel_name='muk_ai.session',
        inverse_name='parent_session_id',
        string='Subagents',
        readonly=True,
    )

    subagents = fields.Json(
        compute='_compute_subagents',
        string='Subagent Run',
        help='The roster of the subagents of a delegating chat.',
    )

    subagent_of = fields.Json(
        compute='_compute_subagents',
        string='Subagent Of',
        help='The chat a subagent works for, and how the run names it.',
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _is_child(self) -> bool:
        """Return whether this chat runs a task for a parent chat."""
        return bool(self.parent_session_id)

    def _delegates(self) -> models.BaseModel:
        """Return the active agents this chat may hand tasks to."""
        if self._is_child() or not self.agent_id.allow_delegation:
            return self.env['muk_ai.agent']
        return self.agent_id.delegate_agent_ids.filtered('active')

    def _run_root(self) -> AISession:
        """Return the chat at the top of the delegation run."""
        return self.parent_session_id or self

    def _run_children(self) -> AISession:
        """Return every subagent of the run, oldest first."""
        return self._run_root().child_session_ids.sorted('id')

    def _live(self) -> AISession:
        """Return the chats of this set that have not ended."""
        return self.filtered(lambda session: session.state not in TERMINAL_STATES)

    def _lock_row(self) -> None:
        """Take the row lock of this chat, so concurrent finishers serialize."""
        self.flush_recordset()
        self.env.cr.execute(
            SQL('SELECT id FROM muk_ai_session WHERE id = %s FOR UPDATE', self.id)
        )
        self.invalidate_recordset(['state', 'pending_ask'])

    def _identity(self) -> dict:
        """Return what names a subagent wherever its run is shown."""
        brief = self.delegation_brief or {}
        return {
            'id': self.id,
            'name': self.name,
            'agent_name': self.agent_id.name or '',
            'objective': brief.get('objective') or '',
            'color': brief.get('color') or CHILD_COLORS[0],
        }

    def _activity(self) -> dict | bool:
        """Return the last step of a working subagent, for the client to word.

        The events belong to the owner of the run; the caller's read access to
        the run was checked by the snapshot that asks.
        """
        event = (
            self.env['muk_ai.session.event']
            .sudo()
            .search(
                [('session_id', '=', self.id), ('kind', 'in', ('tool_call', 'text'))],
                order='sequence desc, id desc',
                limit=1,
            )
        )
        if not event:
            return False
        payload = event.payload or {}
        arguments = payload.get('arguments') or {}
        if len(json.dumps(arguments, default=str)) > ACTIVITY_ARGS_MAX_CHARS:
            arguments = {}
        return {
            'kind': event.kind,
            'name': payload.get('name') or '',
            'arguments': arguments,
        }

    def _roster_entry(self) -> dict:
        """Return what the run shows of one subagent."""
        working = self.state not in TERMINAL_STATES
        waiting = self.state == 'waiting'
        end = fields.Datetime.now() if working else self.write_date
        return {
            **self._identity(),
            'call_id': (self.delegation_brief or {}).get('call_id') or '',
            'state': self.state,
            'stop_reason': self.stop_reason or False,
            'error': self.error_message or False,
            'activity': working and not waiting and self._activity(),
            'repeating': working and bool((self.loop_state or {}).get('noticed')),
            'ask': waiting and self._public_pending_ask(),
            'waiting_since': waiting and fields.Datetime.to_string(self.write_date),
            'elapsed': int((end - self.create_date).total_seconds()),
            'cost': self.total_cost,
            'report': (self.last_text or '')[:REPORT_PREVIEW_CHARS],
        }

    def _run_payload(self) -> dict:
        """Return the roster of the run this chat belongs to."""
        return {
            'children': [child._roster_entry() for child in self._run_children()],
        }

    def _publish_run(self) -> None:
        """Push the roster of the run, and whether it waits for the owner, to its lists."""
        root = self._run_root()
        root._publish_event('subagent_update', root._run_payload())
        root._bus_send_audience(
            'muk_ai.session_state',
            {'session_id': root.id, 'name': root.name, **root._state_metrics()},
        )

    def _report(self) -> dict:
        """Return what the lead learns of a subagent that ended."""
        return {
            'subagent': self.id,
            'agent': self.agent_id.name or '',
            'objective': (self.delegation_brief or {}).get('objective') or '',
            'state': self.state,
            'stop_reason': self.stop_reason or '',
            'report': self.last_text or '',
            'error': self.error_message or '',
        }

    def _delegation_outcome(self, children: AISession) -> dict:
        """Return the result of a lead tool once the subagents it waited for ended."""
        return {
            'status': 'completed',
            'results': [child._report() for child in children],
        }

    def _recent_messages(self, limit: int) -> list[dict]:
        """Return the last messages and tool calls of a subagent, oldest first.

        The events belong to the owner of the run, whose lead asks.
        """
        events = (
            self.env['muk_ai.session.event']
            .sudo()
            .search(
                [
                    ('session_id', '=', self.id),
                    ('kind', 'in', ('user_message', 'text', 'tool_call', 'ask_user')),
                ],
                order='sequence desc, id desc',
                limit=limit,
            )
        )
        roles = {'user_message': 'user', 'text': 'assistant', 'ask_user': 'question'}
        messages = []
        for event in reversed(events):
            payload = event.payload or {}
            if event.kind == 'tool_call':
                arguments = json.dumps(payload.get('arguments') or {}, default=str)
                messages.append(
                    {
                        'role': 'tool_call',
                        'name': payload.get('name') or '',
                        'arguments': arguments[:STATUS_TEXT_CHARS],
                    }
                )
            else:
                text = payload.get('content') or payload.get('text') or ''
                messages.append(
                    {'role': roles[event.kind], 'text': text[:STATUS_TEXT_CHARS]}
                )
        return messages

    def _take_reports(self) -> bool:
        """Hand the lead the reports of the subagents it did not wait for.

        :return: whether a report was handed over
        """
        self.invalidate_recordset(['child_session_ids'])
        children = self.child_session_ids.filtered(
            lambda child: (
                child.state in TERMINAL_STATES
                and (child.delegation_brief or {}).get('notify')
            )
        ).sorted('id')
        for child in children:
            child.delegation_brief = {**child.delegation_brief, 'notify': False}
        self._extend_conversation(
            [
                {
                    'role': 'user',
                    'content': [
                        {'type': 'input_text', 'text': report_notice(child._report())}
                    ],
                    '_notice_entry': True,
                }
                for child in children
            ]
        )
        return bool(children)

    def _spawn_children(
        self, briefs: list[dict], call_id: str, notify: bool
    ) -> AISession:
        """Create and start one subagent per brief of a delegate call.

        They start without the context keys of the delegate call, which their
        workers would otherwise restore.
        """
        context = {
            key: value
            for key, value in self.env.context.items()
            if key not in ('muk_mcp_session_id', 'muk_ai_delegate_call_id')
        }
        Session = self.env(context=context)['muk_ai.session']
        offset = len(self.child_session_ids)
        children = Session.with_context(muk_ai_subagent_spawn=True).create(
            [
                {
                    'name': '%s: %s' % (agent.name, brief['objective'][:60]),
                    'agent_id': agent.id,
                    'user_id': self.user_id.id,
                    'parent_session_id': self.id,
                    'delegation_brief': {
                        **brief,
                        'color': CHILD_COLORS[(offset + index) % len(CHILD_COLORS)],
                        'call_id': call_id,
                        'notify': notify,
                    },
                }
                for index, brief in enumerate(briefs)
                for agent in [Session.env['muk_ai.agent'].browse(brief.pop('agent_id'))]
            ]
        )
        children = Session.browse(children.ids)
        self._append_event(
            {
                'kind': 'delegation_start',
                'call_id': call_id,
                'children': [child._identity() for child in children],
            }
        )
        for child in children:
            child.start(render_brief(child.delegation_brief))
        return children

    def _execute_waiting_call(
        self,
        call: dict,
        tool_calls: list,
        outputs: list,
        index: int,
        has_terminating: bool,
    ) -> bool | None:
        """Run a lead tool and pause the round until the subagents it waits for reported.

        The pause is committed before the subagents are looked at under the row
        lock, so a subagent ending in its own worker finds a waiting parent.
        """
        self._record_tool_call(call)
        self._heartbeat_claim()
        result, ok = self.with_context(
            muk_ai_delegate_call_id=call['call_id']
        )._dispatch_tool_call(call['name'], call['arguments'], call['call_id'])
        self._heartbeat_claim()
        answer = json.loads(result) if ok and isinstance(result, str) else {}
        if answer.get('wait'):
            children = self.browse(answer['subagent_ids'])
            pending = {
                'kind': 'children',
                'call_id': call['call_id'],
                'name': call['name'],
                'arguments': call['arguments'],
                'child_ids': children.ids,
                'tool_calls': tool_calls,
                'outputs': outputs,
                'resume_index': index,
                'has_terminating': has_terminating,
            }
            self.write({'pending_ask': pending})
            self._transition_state('waiting')
            self._commit_safe()
            self._lock_row()
            if self.state != 'waiting' or children._live():
                return None
            self.write({'pending_ask': False})
            self._transition_state('running')
            result = self._delegation_outcome(children)
        self._record_tool_result(
            outputs, call['call_id'], call['name'], result, arguments=call['arguments']
        )
        return False

    def _resume_from_children(self, pending: dict) -> None:
        """Answer the paused delegate call and carry on with the rest of the round."""
        children = self.browse(pending['child_ids']).exists()
        outputs = list(pending['outputs'])
        self._record_tool_result(
            outputs,
            pending['call_id'],
            pending['name'],
            self._delegation_outcome(children),
            arguments=pending['arguments'],
        )
        self.write({'pending_ask': False, 'claimed_at': False})
        self._transition_state('running')
        self._process_tool_round(
            list(pending['tool_calls']),
            outputs,
            pending['resume_index'] + 1,
            has_terminating=bool(pending['has_terminating']),
        )
        if self.state == 'running':
            self._trigger_worker()

    def _resume_parent(self) -> None:
        """Resume the parent under its row lock when every sibling has ended.

        A lead that did not wait for this subagent and has finished its turn is
        woken to read the report.
        """
        parent = self.parent_session_id
        parent._lock_row()
        pending = parent.pending_ask or {}
        if (
            parent.state == 'waiting'
            and pending.get('kind') == 'children'
            and self.id in pending['child_ids']
        ):
            siblings = self.browse(pending['child_ids']).exists()
            siblings.invalidate_recordset(['state'])
            if not siblings._live():
                parent._resume_from_children(pending)
        elif (self.delegation_brief or {}).get('notify') and parent.state == 'done':
            parent.write(parent._turn_start_values())
            parent._transition_state('running')
            parent._trigger_worker()

    def _on_parent(self, action: Callable[[], None]) -> None:
        """Commit this subagent, then run ``action`` on its parent in a fresh transaction.

        The parent may be running and writing its own row meanwhile, so a lost
        serialization is retried here, where nothing would replay it.
        """
        self._commit_safe()
        for attempt in range(LOCK_ATTEMPTS):
            try:
                action()
            except PG_CONCURRENCY_EXCEPTIONS_TO_RETRY:
                if attempt == LOCK_ATTEMPTS - 1:
                    raise
                self.env.cr.rollback()
                self.env.invalidate_all()
                continue
            return

    def _on_child_finished(self) -> None:
        """Tell the run this subagent ended and resume its parent once all have.

        The end is committed before the parent is locked, so of two subagents
        ending together exactly one finds itself last.
        """
        if not self.stop_reason:
            self.stop_reason = {'done': 'done', 'stopped': 'stopped'}.get(
                self.state, 'error'
            )
        self._publish_run()
        self._on_parent(self._resume_parent)

    def _track_repeat(self, output: dict, name: str, arguments, result) -> None:
        """Warn a subagent that repeats a call to no effect, and end it if it goes on."""
        state = dict(self.loop_state or {})
        fingerprint = tool_fingerprint(name, arguments, result)
        recent = [*(state.get('recent') or []), fingerprint][-LOOP_WINDOW:]
        state['recent'] = recent
        repeats = recent.count(fingerprint)
        if repeats == LOOP_NOTICE_REPEATS:
            output['output'] = f'{output["output"]}\n\n{loop_notice(name)}'
            state['noticed'] = True
        elif repeats >= LOOP_HALT_REPEATS:
            state['halt'] = self.env._(
                'No progress: %(tool)s returned the same result %(count)s times.',
                tool=name,
                count=repeats,
            )
        self.loop_state = state

    def _build_delegates_block(self) -> str:
        """Build the prompt block naming the agents this chat leads, and when."""
        return '\n'.join(
            filter(
                None,
                [
                    '<delegates>',
                    'Agents you can delegate to, by exact name:',
                    *(
                        f'- {agent.name}: {agent.description}'
                        if agent.description
                        else f'- {agent.name}'
                        for agent in self._delegates()
                    ),
                    self.agent_id.delegation_instructions,
                    '</delegates>',
                ],
            )
        )

    def _system_prompt_addenda(self) -> list[str]:
        """Tell a subagent what it is, and a delegating agent whom it may use."""
        addenda = super()._system_prompt_addenda()
        if self._is_child():
            addenda.append(SUBAGENT_RULES)
        elif self._delegates():
            addenda.append(self._build_delegates_block())
        return addenda

    def _effective_approval_mode(self) -> str:
        """Keep a subagent asking whenever its parent would ask."""
        if (
            self._is_child()
            and self.parent_session_id._effective_approval_mode() == 'ask'
        ):
            return 'ask'
        return super()._effective_approval_mode()

    def _available_client_kinds(self) -> set[str]:
        """Offer no client-executed tool to a subagent, which no browser tab hosts."""
        return set() if self._is_child() else super()._available_client_kinds()

    def _get_filtered_catalog(self) -> list[dict]:
        """Narrow a subagent to its parent's tools and offer the lead tools to leads."""
        catalog = super()._get_filtered_catalog()
        if self._is_child():
            catalog = self.parent_session_id.agent_id.apply_tool_filter(catalog)
        if not self._delegates():
            catalog = [
                entry for entry in catalog if entry.get('name') not in LEAD_TOOLS
            ]
        return catalog

    @api.model
    def _eager_tool_name_registry(self) -> set[str]:
        """Add the lead tools to the tools a chat may load upfront."""
        return super()._eager_tool_name_registry() | LEAD_TOOLS

    def _eager_tool_names(self) -> set[str]:
        """Load the lead tools upfront for a chat that may delegate."""
        names = super()._eager_tool_names()
        return names | LEAD_TOOLS if self._delegates() else names

    def _should_autoname(self) -> bool:
        """Keep the name a subagent was spawned under."""
        return not self._is_child() and super()._should_autoname()

    def _enforce_tool_scope(self) -> str | None:
        """Keep a subagent read-only whenever its parent is."""
        if self._is_child() and self.parent_session_id._enforce_tool_scope() == 'read':
            return 'read'
        return super()._enforce_tool_scope()

    def _pending_ask_queues_input(self, pending: dict | None = None) -> bool:
        """Queue what is typed while the chat waits for its subagents."""
        pending = self.pending_ask if pending is None else pending
        return (pending or {}).get(
            'kind'
        ) == 'children' or super()._pending_ask_queues_input(pending)

    def _execute_tool_call(
        self,
        call: dict,
        tool_calls: list,
        outputs: list,
        index: int,
        has_terminating: bool,
    ) -> bool | None:
        """Pause the round on a lead tool that waits for subagents."""
        if call['name'] in (DELEGATE_TOOL, MESSAGE_TOOL):
            return self._execute_waiting_call(
                call, tool_calls, outputs, index, has_terminating
            )
        return super()._execute_tool_call(
            call, tool_calls, outputs, index, has_terminating
        )

    def _record_tool_call(self, call: dict) -> None:
        """Show the run what a subagent is doing now."""
        super()._record_tool_call(call)
        if self._is_child():
            self._publish_run()

    def _record_tool_result(
        self,
        outputs: list,
        call_id: str,
        name: str,
        output_result,
        log_result=None,
        arguments: dict | None = None,
    ) -> None:
        """Watch every real tool result of a subagent for repeats."""
        super()._record_tool_result(
            outputs,
            call_id,
            name,
            output_result,
            log_result=log_result,
            arguments=arguments,
        )
        if self._is_child() and log_result is None:
            self._track_repeat(outputs[-1], name, arguments, output_result)

    def _process_tool_round(
        self,
        tool_calls: list,
        outputs: list,
        start_index: int,
        has_terminating: bool = False,
    ) -> bool | None:
        """End a subagent that keeps repeating itself once its round is recorded."""
        result = super()._process_tool_round(
            tool_calls, outputs, start_index, has_terminating=has_terminating
        )
        if (halt := (self.loop_state or {}).get('halt')) and self.state == 'running':
            self.stop_reason = 'no_progress'
            self._transition_state('error', error=halt)
            return None
        return result

    def _stream_provider_round(
        self,
        provider: models.BaseModel,
        tool_schema: list,
        model: str | None,
        agent: models.BaseModel,
        cache: dict | None = None,
        notice: dict | None = None,
    ) -> dict:
        """Hand the lead the reports that arrived before it answers again."""
        self._take_reports()
        return super()._stream_provider_round(
            provider, tool_schema, model, agent, cache=cache, notice=notice
        )

    def _drain_pending_message(self) -> bool:
        """Carry on with the turn for reports that arrived as it ended."""
        taken = self._take_reports()
        return super()._drain_pending_message() or taken

    def _turn_start_values(self) -> dict:
        """Forget why a subagent ended, and its repeats, when it starts again."""
        return {
            **super()._turn_start_values(),
            'stop_reason': False,
            'loop_state': False,
        }

    @api.model
    def _turn_wallclock_seconds(self) -> int:
        """Cap a subagent's turn at what is left of its parent's."""
        seconds = super()._turn_wallclock_seconds()
        if not self._is_child():
            return seconds
        spent = self.parent_session_id.turn_wallclock_spent or 0.0
        return max(int(seconds - spent), WALLCLOCK_MIN_SECONDS)

    def _turn_cost_error(self, limit: float) -> None:
        """Name the budget as the reason a subagent ended on cost."""
        if self._is_child():
            self.stop_reason = 'budget'
        super()._turn_cost_error(limit)

    def _turn_budget_error(self, turn_budget: float) -> None:
        """Name the budget as the reason a subagent ended on time."""
        if self._is_child():
            self.stop_reason = 'budget'
        super()._turn_budget_error(turn_budget)

    def _max_iterations_error(self) -> None:
        """Name the iteration cap as the reason a subagent ended."""
        if self._is_child():
            self.stop_reason = 'max_iterations'
        super()._max_iterations_error()

    def _publish_event(self, event_type: str, payload: dict) -> None:
        """Report a subagent's state changes to its run.

        A subagent that finishes with direction queued goes on to follow it,
        so it has not ended yet.
        """
        super()._publish_event(event_type, payload)
        if (
            event_type != 'state'
            or not self._is_child()
            or self.env.context.get('muk_ai_skip_done_notification')
        ):
            return
        state = payload.get('state')
        if state in TERMINAL_STATES and not (state == 'done' and self.pending_ids):
            self._on_child_finished()
        else:
            self._publish_run()

    def _notify_state_transition(self, payload: dict) -> None:
        """Tell the owner through the parent chat when a subagent waits for them.

        The parent's card takes the answer; a parent pausing for its
        subagents and a subagent ending are shown by the run itself.
        """
        state = payload.get('state')
        ask = payload.get('ask') or self.pending_ask or {}
        if self._is_child():
            if state == 'waiting':
                notice = {
                    'state': 'waiting',
                    'ask': {
                        'kind': 'subagent',
                        'agent_name': self.agent_id.name or self.name,
                        'approval': ask.get('kind') == 'approval',
                    },
                }
                self._on_parent(
                    lambda: self.parent_session_id._notify_state_transition(notice)
                )
            return
        if state != 'waiting' or ask.get('kind') != 'children':
            super()._notify_state_transition(payload)

    def _notification_summary(
        self, new_state: str, payload: dict, ask_kind: str | None
    ) -> tuple[str, str]:
        """Say which subagent waits for the owner, and for what."""
        if ask_kind != 'subagent':
            return super()._notification_summary(new_state, payload, ask_kind)
        ask = payload['ask']
        if ask['approval']:
            return (
                self.env._('AI session needs approval'),
                self.env._(
                    '%s needs your approval before running a tool', ask['agent_name']
                ),
            )
        return (
            self.env._('AI session needs your input'),
            self.env._('%s is asking you a question', ask['agent_name']),
        )

    @api.model
    def _rate_limit_domain(self) -> list:
        """Count the chats the user started, never the subagents they spawned."""
        return [*super()._rate_limit_domain(), ('parent_session_id', '=', False)]

    @api.model
    def _check_rate_limit(self, batch_size: int = 1) -> None:
        """Leave the subagents of a delegation out of the per-minute chat limit.

        :raise UserError: when the per-minute rate limit would be exceeded
        """
        if not self.env.context.get('muk_ai_subagent_spawn'):
            super()._check_rate_limit(batch_size)

    @api.model
    def _gc_sessions_older_than(self, days: int, domain: Domain) -> tuple[int, int]:
        """Delete subagents only with their parent, never before it."""
        return super()._gc_sessions_older_than(
            days, domain & Domain('parent_session_id', '=', False)
        )

    # ----------------------------------------------------------
    # Actions
    # ----------------------------------------------------------

    def get_snapshot(self, include_conversation: bool = False) -> dict:
        """Add the run of a delegating chat, or the parent of a subagent."""
        return {
            **super().get_snapshot(include_conversation=include_conversation),
            'subagents': self.subagents,
            'subagent_of': self.subagent_of,
        }

    def action_stop(self) -> dict:
        """Stop the chat and every subagent still running for it."""
        result = super().action_stop()
        if live := self.child_session_ids._live():
            for child in live:
                child.action_stop()
            result = self.get_snapshot()
        return result

    def action_stop_subagents(self) -> dict:
        """Stop every subagent of the run still running and return the snapshot."""
        self.ensure_one()
        for child in self._run_children()._live():
            child.action_stop()
        return self.get_snapshot()

    def action_handover(self, new_user_id: int) -> bool:
        """Hand the subagents over with their parent, which only an idle run allows.

        :raise UserError: when this chat is a subagent or one of its subagents runs
        """
        if self._is_child():
            raise UserError(
                self.env._('A subagent is handed over with the chat it works for.')
            )
        if self.child_session_ids._live():
            raise UserError(
                self.env._('Stop the subagents before handing the chat over.')
            )
        result = super().action_handover(new_user_id)
        self.child_session_ids.write(
            {'user_id': self.user_id.id, 'user_context': self.user_context}
        )
        return result

    # ----------------------------------------------------------
    # Compute
    # ----------------------------------------------------------

    def _compute_subagents(self) -> None:
        """Describe the run of a delegating chat, or the parent of a subagent."""
        for record in self:
            parent = record.parent_session_id
            record.subagents = (
                record._run_payload()
                if record.child_session_ids and not parent
                else False
            )
            record.subagent_of = (
                {
                    **record._identity(),
                    'parent_id': parent.id,
                    'parent_name': parent.name,
                }
                if parent
                else False
            )

    @api.depends('state', 'pending_ask', 'child_session_ids.state')
    def _compute_awaiting_user(self) -> None:
        """Flag a lead while a subagent asks, not while it only waits for one."""
        super()._compute_awaiting_user()
        for record in self.filtered('child_session_ids'):
            paused = (record.pending_ask or {}).get('kind') == 'children'
            record.awaiting_user = (
                record.awaiting_user and not paused
            ) or 'waiting' in record.child_session_ids.mapped('state')
