from __future__ import annotations

import json
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Domain
from odoo.service.model import PG_CONCURRENCY_EXCEPTIONS_TO_RETRY
from odoo.tools import SQL

from odoo.addons.muk_ai.tools import WALLCLOCK_MIN_SECONDS
from odoo.addons.muk_ai_subagents.tools import (
    CHILD_COLORS,
    DEFAULT_RUN_COST_LIMIT,
    DEFAULT_STALL_SECONDS,
    DELEGATE_TOOL,
    DELEGATION_SKIP_REASON,
    LOCK_ATTEMPTS,
    LOOP_REPEATS,
    LOOP_WINDOW,
    LOOP_WITHHOLD_ROUNDS,
    STEER_MAX_CHARS,
    STEER_MAX_QUEUED,
    STOP_REASONS,
    SUBAGENT_RULES,
    SUMMARY_MAX_CHARS,
    TERMINAL_STATES,
    WITHHELD_SKIP_REASON,
    loop_notice,
    render_brief,
    tool_fingerprint,
)


class AISession(models.Model):
    """Run focused child sessions on behalf of a parent and report back."""

    _inherit = 'muk_ai.session'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    parent_session_id = fields.Many2one(
        comodel_name='muk_ai.session',
        string='Parent Session',
        help='Session whose delegate call started this one.',
        readonly=True,
        index=True,
        copy=False,
        ondelete='cascade',
    )

    delegation_brief = fields.Json(
        string='Delegation Brief',
        help='Task the parent handed over, plus the colour and call it belongs to.',
        readonly=True,
        copy=False,
    )

    stop_reason = fields.Selection(
        selection=STOP_REASONS,
        string='Stop Reason',
        help='Why a subagent session ended, set on every terminal path.',
        readonly=True,
        copy=False,
    )

    heartbeat_at = fields.Datetime(
        string='Heartbeat',
        help='Last time a subagent session completed a provider round.',
        readonly=True,
        copy=False,
    )

    loop_state = fields.Json(
        string='Loop State',
        help='Recent tool-call fingerprints and the tools withheld for repeating.',
        readonly=True,
        copy=False,
    )

    child_session_ids = fields.One2many(
        comodel_name='muk_ai.session',
        string='Subagent Sessions',
        readonly=True,
        inverse_name='parent_session_id',
    )

    child_session_count = fields.Integer(
        compute='_compute_child_session_count',
        string='Subagents',
    )

    # ----------------------------------------------------------
    # Helper Run Tree
    # ----------------------------------------------------------

    def _is_child(self) -> bool:
        """Return whether this session runs a task for a parent."""
        return bool(self.id and self.parent_session_id)

    def _can_delegate(self) -> bool:
        """Return whether this session may hand tasks to subagent agents."""
        agent = self.agent_id
        return bool(
            not self._is_child() and agent.allow_delegation and agent.delegate_agent_ids
        )

    def _run_root(self) -> AISession:
        """Return the top session of the delegation run."""
        return self.parent_session_id or self

    def _parent_as_owner(self) -> AISession:
        """Return the parent acting as whoever owns it now, under its own context.

        A subagent keeps running as the user who spawned it, so once the
        parent changed hands its worker may only read the parent; what it
        reports back has to be written as the new owner. The context is the
        one the parent stored for itself: a subagent ends in a worker or a
        sweep whose environment knows nothing of the owner's language or
        companies, and may still carry those of whoever spawned it.
        """
        parent = self.parent_session_id.sudo()
        return parent.with_user(parent.user_id).with_context(
            **(parent.user_context or {})
        )

    def _run_children(self) -> AISession:
        """Return every subagent of the run, oldest first, with elevated rights.

        A subagent is owned by whoever spawned it; whoever holds the run now
        acts on them through the parent, whose rights the caller checked.
        """
        return self._run_root().sudo().child_session_ids.sorted('id')

    def _run_child(self, child_id: int) -> AISession:
        """Return the subagent of this run with the given id.

        :raise UserError: when no subagent of the run carries the id
        """
        child = self._run_children().filtered(lambda c: c.id == child_id)
        if not child:
            raise UserError(_('No subagent %(id)s belongs to this run.', id=child_id))
        return child

    def _live(self) -> AISession:
        """Return the sessions of this set that have not ended."""
        return self.filtered(lambda s: s.state not in TERMINAL_STATES)

    def _run_cost(self) -> float:
        """Return what the run has spent so far, root and subagents together."""
        root = self._run_root()
        return sum((root | root.child_session_ids).mapped('total_cost'))

    @api.model
    def _run_cost_limit(self) -> float:
        """Return the configured per-run cost limit, or ``0.0`` when disabled."""
        raw = (
            self.env['ir.config_parameter']
            .sudo()
            .get_param('muk_ai_subagents.run_cost_limit')
        )
        if raw is False:
            return DEFAULT_RUN_COST_LIMIT
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return DEFAULT_RUN_COST_LIMIT
        return value if value > 0 else 0.0

    @api.model
    def _stall_seconds(self) -> int:
        """Return the seconds of silence after which a subagent counts as stalled."""
        return self._int_config_param(
            'muk_ai_subagents.stall_timeout', DEFAULT_STALL_SECONDS
        )

    def _child_color(self) -> str:
        """Return the colour this subagent was given at spawn."""
        return (self.delegation_brief or {}).get('color') or CHILD_COLORS[0]

    def _elapsed_seconds(self) -> int:
        """Return how long this session has run, frozen once it ended."""
        end = self.write_date if self.state in TERMINAL_STATES else None
        end = end or fields.Datetime.now()
        return int((end - self.create_date).total_seconds()) if self.create_date else 0

    def _lock_row(self) -> None:
        """Take the row lock of this session so concurrent finishers serialize."""
        self.flush_recordset()
        self.env.cr.execute(
            SQL('SELECT id FROM muk_ai_session WHERE id = %s FOR UPDATE', self.id)
        )
        self.invalidate_recordset(['state', 'pending_ask'])

    def _children_of_call(self, call_id: str) -> AISession:
        """Return the subagents of one delegate call, in the order it named them.

        Sorted explicitly: a session is ordered newest first, which would
        hand the model a three-task brief's reports backwards.
        """
        self.invalidate_recordset(['child_session_ids'])
        return self.child_session_ids.filtered(
            lambda child: (child.delegation_brief or {}).get('call_id') == call_id
        ).sorted('id')

    # ----------------------------------------------------------
    # Helper Roster
    # ----------------------------------------------------------

    def _roster_identity(self) -> dict:
        """Return what names a subagent in the parent conversation."""
        return {
            'id': self.id,
            'name': self.name,
            'agent_name': self.agent_id.name or '',
            'color': self._child_color(),
        }

    def _activity(self) -> str:
        """Describe what a subagent is doing right now, from its last event."""
        if self.state == 'waiting':
            return _('Waiting for your decision')
        if self.state in TERMINAL_STATES:
            labels = dict(self._fields['stop_reason']._description_selection(self.env))
            return labels.get(self.stop_reason, self.state)
        # Events stay with whoever spawned the subagent; its session was checked.
        Event = self.env['muk_ai.session.event'].sudo()
        event = Event.search(
            [('session_id', '=', self.id)], order='sequence desc, id desc', limit=1
        )
        payload = event.payload or {}
        if event.kind == 'tool_call':
            return _('Calling %(tool)s', tool=payload.get('name') or '')
        if event.kind == 'tool_result':
            return _('Reading the result of %(tool)s', tool=payload.get('name') or '')
        if event.kind == 'text':
            return _('Writing')
        return _('Thinking')

    def _roster_entry(self) -> dict:
        """Return the roster line the parent conversation shows for a subagent."""
        return {
            **self._roster_identity(),
            'state': self.state,
            'activity': self._activity(),
            'elapsed': self._elapsed_seconds(),
            'cost': round(self.total_cost or 0.0, 6),
            'stop_reason': self.stop_reason or False,
            'stuck': self._is_going_nowhere(),
            'waiting': (
                self._public_pending_ask() if self.state == 'waiting' else None
            ),
            'waiting_since': (
                fields.Datetime.to_string(self.write_date)
                if self.state == 'waiting'
                else False
            ),
            'summary': (self.last_text or '')[:SUMMARY_MAX_CHARS],
        }

    def _roster_result(self) -> dict:
        """Return the event payload reporting a finished subagent to the parent."""
        return {
            'child_id': self.id,
            'name': self.name,
            'agent_name': self.agent_id.name or '',
            'color': self._child_color(),
            'summary': (self.last_text or '')[:SUMMARY_MAX_CHARS],
            'stop_reason': self.stop_reason or False,
            'duration': self._elapsed_seconds(),
            'cost': round(self.total_cost or 0.0, 6),
        }

    def _delegation_result(self) -> dict:
        """Return what the parent model receives for a finished subagent."""
        brief = self.delegation_brief or {}
        return {
            'child_id': self.id,
            'agent': self.agent_id.name or '',
            'objective': brief.get('objective') or '',
            'state': self.state,
            'stop_reason': self.stop_reason or '',
            'report': self.last_text or '',
            'error': self.error_message or '',
            'cost': round(self.total_cost or 0.0, 6),
            'duration': self._elapsed_seconds(),
        }

    def _delegation_outcome(self, children: AISession) -> dict:
        """Return the tool result of a delegate call whose subagents all reported."""
        return {
            'status': 'completed',
            'results': [child._delegation_result() for child in children],
        }

    def _has_escalation(self) -> bool:
        """Tell whether a subagent of the run is waiting on the user."""
        return any(
            child.state == 'waiting' and child.pending_ask
            for child in self._run_children()
        )

    def _publish_subagent_update(self) -> None:
        """Push the current roster to whoever is watching the parent."""
        self._publish_event('subagent_update', self.subagent_run_snapshot())

    # ----------------------------------------------------------
    # Helper Spawn
    # ----------------------------------------------------------

    def _spawn_children(self, briefs: list[dict]) -> AISession:
        """Create and start one subagent session per brief.

        Each brief carries the ``agent_id`` the tool resolved. The subagents
        start under a context stripped of the MCP session keys of the parent
        call, so nothing of the parent leaks into what their workers restore.
        """
        call_id = self.env.context.get('muk_ai_delegate_call_id') or ''
        context = {
            key: value
            for key, value in self.env.context.items()
            if key not in ('muk_mcp_session_id', 'muk_ai_delegate_call_id')
        }
        env = self.env(context=context)
        Session, Agent = env['muk_ai.session'], env['muk_ai.agent']
        offset = len(self.child_session_ids)
        children = Session
        for index, brief in enumerate(briefs):
            agent = Agent.browse(brief.pop('agent_id'))
            color = CHILD_COLORS[(offset + index) % len(CHILD_COLORS)]
            child = Session.with_context(muk_ai_subagent_spawn=True).create(
                {
                    'name': f'{agent.name}: {brief["objective"][:60]}',
                    'agent_id': agent.id,
                    'user_id': self.user_id.id,
                    'parent_session_id': self.id,
                    'delegation_brief': {
                        **brief,
                        'color': color,
                        'call_id': call_id,
                    },
                }
            )
            children |= Session.browse(child.id)
        self._append_event(
            {
                'kind': 'delegation_start',
                'children': [child._roster_identity() for child in children],
            }
        )
        for child in children:
            child.start(render_brief(child.delegation_brief))
        return children

    # ----------------------------------------------------------
    # Helper Hand-off
    # ----------------------------------------------------------

    def _execute_delegate_call(
        self,
        call: dict,
        tool_calls: list,
        outputs: list,
        index: int,
        has_terminating: bool,
    ) -> bool | None:
        """Run a delegate call and park the turn until its subagents report.

        The park is committed before the subagents' state is read back under
        the row lock, so a subagent ending in its own worker finds a waiting parent.
        """
        self._record_tool_call(call)
        self._heartbeat_claim()
        result, ok = self.with_context(
            muk_ai_delegate_call_id=call['call_id']
        )._dispatch_tool_call(call['name'], call['arguments'], call['call_id'])
        self._heartbeat_claim()
        children = self._children_of_call(call['call_id'])
        if not ok or not children:
            self._record_tool_result(
                outputs,
                call['call_id'],
                call['name'],
                result,
                arguments=call['arguments'],
            )
            return False
        pending = {
            'kind': 'children',
            'call_id': call['call_id'],
            'arguments': call['arguments'],
            'text': _(
                'Waiting for %(count)s subagent(s) to report.', count=len(children)
            ),
            'child_ids': children.ids,
            'tool_calls': tool_calls,
            'outputs': outputs,
            'resume_index': len(tool_calls) - 1,
            'has_terminating': has_terminating,
        }
        self.write({'state': 'waiting', 'pending_ask': pending})
        self._publish_event(
            'state', {'state': 'waiting', 'ask': self._public_pending_ask(pending)}
        )
        self.flush_recordset()
        self._commit_safe()
        self._lock_row()
        children.invalidate_recordset(['state'])
        if self.state != 'waiting':
            return None
        if not children._live():
            self.write({'pending_ask': False})
            self._transition_state('running')
            self._record_tool_result(
                outputs,
                call['call_id'],
                call['name'],
                self._delegation_outcome(children),
                arguments=call['arguments'],
            )
            return False
        for later in tool_calls[index + 1 :]:
            self._record_tool_call(later)
            self._skip_tool_call(
                outputs, later, DELEGATION_SKIP_REASON, log_result={'error': 'skipped'}
            )
        self.write({'pending_ask': {**pending, 'outputs': outputs}})
        return None

    def _resume_from_children(self, pending: dict) -> None:
        """Answer the parked delegate call and hand the turn back to a worker."""
        children = self.browse(pending.get('child_ids') or []).exists()
        tool_calls = list(pending.get('tool_calls') or [])
        outputs = list(pending.get('outputs') or [])
        self._record_tool_result(
            outputs,
            pending['call_id'],
            DELEGATE_TOOL,
            self._delegation_outcome(children),
            arguments=pending.get('arguments'),
        )
        self.write({'pending_ask': False, 'claimed_at': False})
        self._transition_state('running')
        self._process_tool_round(
            tool_calls,
            outputs,
            len(tool_calls),
            has_terminating=bool(pending.get('has_terminating')),
        )
        self._trigger_worker()

    def _on_child_finished(self) -> None:
        """Report this subagent to its parent and resume it once all have ended.

        A subagent commits its own end before locking the parent, so exactly
        one of two simultaneous finishers finds itself last. The delivered
        flag is claimed after the lock and left to the same transaction as
        the report: committing it first would leave it set with nothing
        delivered if the resume then failed. The serialisation failure is
        retried here because a subagent also ends inside a cron sweep, where
        nothing would replay it. The roster is pushed first either way, so a
        subagent that stopped after the run ended does not read as busy.
        """
        self._parent_as_owner()._publish_subagent_update()
        if (self.delegation_brief or {}).get('delivered'):
            return
        self._commit_safe()
        for attempt in range(LOCK_ATTEMPTS):
            try:
                self._deliver_to_parent()
            except PG_CONCURRENCY_EXCEPTIONS_TO_RETRY:
                if attempt == LOCK_ATTEMPTS - 1:
                    raise
                self.env.cr.rollback()
                self.env.invalidate_all()
                continue
            return

    def _deliver_to_parent(self) -> None:
        """Report this subagent to its parent under the parent's row lock."""
        parent = self._parent_as_owner()
        parent._lock_row()
        self.invalidate_recordset(['delegation_brief'])
        brief = dict(self.delegation_brief or {})
        if brief.get('delivered'):
            return
        self.delegation_brief = {**brief, 'delivered': True}
        parent._append_event({'kind': 'delegation_result', **self._roster_result()})
        parent._publish_subagent_update()
        pending = parent.pending_ask or {}
        if (
            parent.state != 'waiting'
            or pending.get('kind') != 'children'
            or self.id not in (pending.get('child_ids') or [])
        ):
            return
        siblings = self.browse(pending['child_ids']).exists()
        siblings.invalidate_recordset(['state'])
        if siblings._live():
            return
        parent._resume_from_children(pending)

    def _settle_stop_reason(self, state: str) -> None:
        """Record why a subagent ended, unless the ending path already said."""
        if self.stop_reason:
            return
        self.stop_reason = {'done': 'done', 'stopped': 'stopped'}.get(state, 'error')

    def _mark_stalled(self) -> None:
        """Stop a subagent that went quiet and keep what it produced so far."""
        self.write(
            {
                'stop_reason': 'stalled',
                'state': 'stopped',
                'pending_ask': False,
                'error_message': _(
                    'No activity for %(seconds)s seconds.',
                    seconds=self._stall_seconds(),
                ),
            }
        )
        self._publish_event('state', {'state': 'stopped'})

    # ----------------------------------------------------------
    # Helper Loop
    # ----------------------------------------------------------

    def _is_going_nowhere(self) -> bool:
        """Tell whether this subagent is repeating itself instead of progressing.

        The loop ladder withholds a tool that keeps returning the same
        result, which is the earliest honest signal that a subagent is stuck.
        """
        state = self.loop_state or {}
        return bool(state.get('halt') or state.get('withheld'))

    def _withheld_tool_names(self) -> set[str]:
        """Return the tools withheld from this session for repeating themselves."""
        return set((self.loop_state or {}).get('withheld') or {})

    def _accept_steer(self, text: str) -> None:
        """Queue direction for this subagent and tell its parent it happened.

        :raise UserError: when the subagent's queue is full or it has already ended
        """
        self.ensure_one()
        if len(self.pending_ids) >= STEER_MAX_QUEUED:
            raise UserError(
                _(
                    '%(name)s already has %(count)s messages waiting; let it '
                    'act on those first.',
                    name=self.agent_id.name or self.name,
                    count=len(self.pending_ids),
                )
            )
        queued = self.enqueue_message(text)
        if isinstance(queued, dict) and queued.get('queue_rejected_state'):
            raise UserError(
                _(
                    '%(name)s has already finished, so it cannot be given more '
                    'direction. Delegate again if there is more to do.',
                    name=self.agent_id.name or self.name,
                )
            )
        self.parent_session_id._note_steer(self, text)

    def _note_steer(self, child: AISession, text: str) -> None:
        """Record in the parent that a subagent was given direction."""
        self._append_event(
            {
                'kind': 'delegation_steer',
                **child._roster_identity(),
                'text': text[:SUMMARY_MAX_CHARS],
            }
        )
        self._publish_subagent_update()

    def _drain_pending_message(self) -> bool:
        """Fold direction into a subagent's running turn instead of a new one.

        A fresh turn would reset the cost and wall-clock budgets; direction
        that arrives after the subagent ended is dropped so it never restarts.
        """
        if not self._is_child():
            return super()._drain_pending_message()
        pending = self.pending_ids
        if not pending:
            return False
        contents = (
            [p.content or '' for p in pending if (p.content or '').strip()]
            if self.state == 'running'
            else []
        )
        pending.unlink()
        self.invalidate_recordset(['pending_ids'])
        self._publish_event('queue', {'pending': []})
        if not contents:
            return False
        text = '\n\n'.join(contents)
        attachments = self.env['ir.attachment']
        if entry := self._build_user_entry(text, attachments):
            self._extend_conversation([entry])
        self._append_event(self._user_message_log(text, attachments))
        return True

    def _tick_round(self) -> None:
        """Stamp the heartbeat and elapse a withholding round."""
        state = dict(self.loop_state or {})
        withheld = {
            name: rounds - 1
            for name, rounds in (state.get('withheld') or {}).items()
            if rounds > 1
        }
        self.write(
            {
                'heartbeat_at': fields.Datetime.now(),
                'loop_state': {**state, 'withheld': withheld},
            }
        )

    def _track_tool_fingerprint(
        self, outputs: list, name: str, arguments: dict | None, result
    ) -> None:
        """Climb the loop ladder when a call keeps returning the same result.

        The third identical call within the window earns a notice, the
        fourth withholds the tool for two rounds, the fifth ends the session
        once the round has been recorded.
        """
        state = dict(self.loop_state or {})
        fingerprint = tool_fingerprint(name, arguments, result)
        recent = [*(state.get('recent') or []), fingerprint][-LOOP_WINDOW:]
        state['recent'] = recent
        if recent.count(fingerprint) >= LOOP_REPEATS:
            strikes = dict(state.get('strikes') or {})
            level = strikes.get(fingerprint, 0) + 1
            strikes[fingerprint] = level
            state['strikes'] = strikes
            if level == 1:
                outputs.append(loop_notice(name))
            elif level == 2:
                withheld = dict(state.get('withheld') or {})
                withheld[name] = LOOP_WITHHOLD_ROUNDS
                state['withheld'] = withheld
                outputs.append(loop_notice(name, withheld=True))
            else:
                state['halt'] = _(
                    'No progress: %(tool)s returned the same result %(count)s times.',
                    tool=name,
                    count=recent.count(fingerprint),
                )
        self.loop_state = state

    # ----------------------------------------------------------
    # Helper Prompt
    # ----------------------------------------------------------

    def _build_delegates_block(self) -> str:
        """Build the prompt block naming the agents this session may delegate to."""
        lines = [
            '<delegates>',
            (
                'Agents you may hand focused tasks to with the delegate tool, by '
                'exact name:'
            ),
            *(
                f'- {agent.name}: {agent.description}'
                if agent.description
                else f'- {agent.name}'
                for agent in self.agent_id.delegate_agent_ids.filtered('active')
            ),
            '</delegates>',
        ]
        return '\n'.join(lines)

    # ----------------------------------------------------------
    # Actions
    # ----------------------------------------------------------

    def action_open_children(self) -> dict:
        """Return a window action listing the subagents of this session."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Subagents'),
            'res_model': 'muk_ai.session',
            'view_mode': 'list,form',
            'domain': [('parent_session_id', '=', self.id)],
        }

    def action_stop(self) -> dict:
        """Stop the session and every subagent still running for it."""
        result = super().action_stop()
        if live := self.sudo().child_session_ids._live():
            for child in live:
                child.action_stop()
            result = self.get_snapshot()
        return result

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    def subagent_run_snapshot(self) -> dict:
        """Return the roster of the run this session belongs to."""
        self.ensure_one()
        self.check_access('read')
        root = self._run_root()
        return {
            'children': [child._roster_entry() for child in self._run_children()],
            'total_cost': round(root._run_cost(), 6),
            'cost_limit': self._run_cost_limit(),
            'root_id': root.id,
        }

    def subagent_steer(self, child_id: int, message: str) -> dict:
        """Send the user's own direction to one subagent of the run.

        A subagent still working takes it at its next round; one that has
        already reported is asked again, on a fresh turn of its own.

        :raise AccessError: when the caller may only read the run
        :raise UserError: when the subagent's queue is already full
        """
        self.ensure_one()
        self.check_access('write')
        text = (message or '').strip()[:STEER_MAX_CHARS]
        if not text:
            return self.subagent_run_snapshot()
        child = self._run_child(child_id)
        if child.state not in TERMINAL_STATES:
            child._accept_steer(text)
            return self.subagent_run_snapshot()
        if self._run_is_live():
            raise UserError(
                _(
                    '%(name)s has already reported and the run is still '
                    'going. Wait for the others to finish, then ask it for '
                    'more.',
                    name=child.agent_id.name or child.name,
                )
            )
        child.send_message(text)
        self._note_steer(child, text)
        return self.subagent_run_snapshot()

    def _run_is_live(self) -> bool:
        """Tell whether this chat is still parked on a delegation run.

        A subagent that has already reported must not be restarted while the
        run is open: its report has been counted and it would re-enter the
        roster as live.
        """
        self.ensure_one()
        pending = self.pending_ask or {}
        return self.state == 'waiting' and pending.get('kind') == 'children'

    def subagent_stop(self, child_id: int) -> dict:
        """Stop one subagent of the run and return the roster.

        :raise AccessError: when the caller may only read the run
        """
        self.ensure_one()
        self.check_access('write')
        self._run_child(child_id).action_stop()
        return self.subagent_run_snapshot()

    def subagent_stop_all(self) -> dict:
        """Stop every subagent of the run still running and return the roster.

        :raise AccessError: when the caller may only read the run
        """
        self.ensure_one()
        self.check_access('write')
        for child in self._run_children()._live():
            child.action_stop()
        return self.subagent_run_snapshot()

    def subagent_peek(self, child_id: int) -> list[dict]:
        """Return the last tool calls of a subagent, oldest first."""
        self.ensure_one()
        self.check_access('read')
        child = self._run_child(child_id)
        calls = (
            self.env['muk_ai.session.event']
            .sudo()
            .search(
                [('session_id', '=', child.id), ('kind', '=', 'tool_call')],
                order='sequence desc, id desc',
                limit=5,
            )
        )
        return [
            {
                'name': (event.payload or {}).get('name') or '',
                'arguments': json.dumps(
                    (event.payload or {}).get('arguments') or {}, default=str
                )[:200],
            }
            for event in reversed(calls)
        ]

    # ----------------------------------------------------------
    # Overrides
    # ----------------------------------------------------------

    def _system_prompt_addenda(self) -> list[str]:
        """Tell a subagent what it is, and a delegating agent whom it may use."""
        addenda = super()._system_prompt_addenda()
        if self._is_child():
            addenda.append(SUBAGENT_RULES)
        elif self._can_delegate():
            addenda.append(self._build_delegates_block())
        return addenda

    def _effective_approval_mode(self) -> str:
        """Keep a subagent asking whenever its parent would have to ask."""
        mode = super()._effective_approval_mode()
        if (
            self._is_child()
            and self.parent_session_id._effective_approval_mode() == 'ask'
        ):
            return 'ask'
        return mode

    def _enforce_tool_scope(self) -> str | None:
        """Keep a subagent read-only whenever its parent is."""
        if self._is_child() and self.parent_session_id._enforce_tool_scope() == 'read':
            return 'read'
        return super()._enforce_tool_scope()

    def _available_client_kinds(self) -> set[str]:
        """Offer no client-executed tool to a subagent, which no tab hosts."""
        if self._is_child():
            return set()
        return super()._available_client_kinds()

    def _get_filtered_catalog(self) -> list[dict]:
        """Narrow a subagent to its parent's tools and hide what is withheld."""
        catalog = super()._get_filtered_catalog()
        if self._is_child() and (parent_agent := self.parent_session_id.agent_id):
            catalog = parent_agent.apply_tool_filter(catalog)
        hidden = self._withheld_tool_names()
        if not self._can_delegate():
            hidden.add(DELEGATE_TOOL)
        return [entry for entry in catalog if entry.get('name') not in hidden]

    @api.model
    def _eager_tool_name_registry(self) -> set[str]:
        """Add the delegate tool to what the session loads itself."""
        return super()._eager_tool_name_registry() | {DELEGATE_TOOL}

    def _eager_tool_names(self) -> set[str]:
        """Ship the delegate tool upfront to a session that may use it."""
        names = super()._eager_tool_names()
        return names | {DELEGATE_TOOL} if self._can_delegate() else names

    def _should_autoname(self) -> bool:
        """Keep the name a subagent was spawned under."""
        if self._is_child():
            return False
        return super()._should_autoname()

    def _should_notify_state(self) -> bool:
        """Stay quiet for a subagent, whose parent conversation shows the run."""
        if self._is_child():
            return False
        return super()._should_notify_state()

    def _pending_ask_queues_input(self, pending: dict | None = None) -> bool:
        """Queue what is typed while the session waits for its subagents."""
        pending = self.pending_ask if pending is None else pending
        return (
            super()._pending_ask_queues_input(pending)
            or (pending or {}).get('kind') == 'children'
        )

    def _public_pending_ask(self, pending: dict | None = None) -> dict | None:
        """Add the roster and the subagents' own asks to a delegation pause."""
        public = super()._public_pending_ask(pending)
        if public and public.get('kind') == 'children':
            children = self.browse(public.get('child_ids') or []).exists()
            public['children'] = [child._roster_entry() for child in children]
        return public

    def _notify_state_transition(self, payload: dict) -> None:
        """Tell the owner about a delegation pause only when a subagent asks."""
        ask = (payload or {}).get('ask') or self.pending_ask or {}
        if (
            (payload or {}).get('state') == 'waiting'
            and isinstance(ask, dict)
            and ask.get('kind') == 'children'
            and not self._has_escalation()
        ):
            return
        super()._notify_state_transition(payload)

    def _notification_summary(
        self, new_state: str, payload: dict, ask_kind: str | None
    ) -> tuple[str, str]:
        """Word the notification of a subagent waiting on the user."""
        if new_state == 'waiting' and ask_kind == 'children':
            return (
                _('AI session needs your input'),
                _(
                    'A subagent of “%(name)s” is waiting for your decision.',
                    name=self.name or _('AI Session'),
                ),
            )
        return super()._notification_summary(new_state, payload, ask_kind)

    def _publish_event(self, event_type: str, payload: dict) -> None:
        """Mirror a subagent's state changes onto its parent."""
        super()._publish_event(event_type, payload)
        if (
            event_type != 'state'
            or not self._is_child()
            or self.env.context.get('muk_ai_skip_done_notification')
        ):
            return
        state = (payload or {}).get('state')
        if state in TERMINAL_STATES:
            self._settle_stop_reason(state)
            self._on_child_finished()
            return
        parent = self._parent_as_owner()
        parent._publish_subagent_update()
        if state == 'waiting' and (parent.pending_ask or {}).get('kind') == 'children':
            parent._publish_event(
                'state', {'state': 'waiting', 'ask': parent._public_pending_ask()}
            )

    @api.model
    def _turn_wallclock_seconds(self) -> int:
        """Cap a subagent's turn at what is left of its parent's."""
        seconds = super()._turn_wallclock_seconds()
        if not self._is_child():
            return seconds
        spent = self.parent_session_id.turn_wallclock_spent or 0.0
        return max(int(seconds - spent), WALLCLOCK_MIN_SECONDS)

    @api.model
    def _turn_cost_limit(self) -> float:
        """Cap a subagent's turn at what is left of the run budget."""
        limit = super()._turn_cost_limit()
        if not self._is_child() or not (run_limit := self._run_cost_limit()):
            return limit
        effective = (self.turn_cost_spent or 0.0) + max(
            run_limit - self._run_cost(), 0.0
        )
        return min(limit, effective) if limit else effective

    def _turn_cost_error(self, limit: float) -> None:
        """Name the budget as the reason a subagent ends on cost."""
        if self._is_child():
            self.stop_reason = 'budget'
        super()._turn_cost_error(limit)

    def _turn_budget_error(self, turn_budget: float) -> None:
        """Name the budget as the reason a subagent ends on time."""
        if self._is_child():
            self.stop_reason = 'budget'
        super()._turn_budget_error(turn_budget)

    def _stream_provider_round(
        self,
        provider: models.BaseModel,
        tool_schema: list,
        model: str | None,
        agent: models.BaseModel,
        cache: dict | None = None,
        notice: dict | None = None,
    ) -> dict:
        """Stamp a subagent's heartbeat before every provider round."""
        if self._is_child():
            self._tick_round()
        return super()._stream_provider_round(
            provider, tool_schema, model, agent, cache=cache, notice=notice
        )

    def _max_iterations_error(self) -> None:
        """Name the iteration cap as the reason a subagent ended."""
        if self._is_child():
            self.stop_reason = 'max_iterations'
        super()._max_iterations_error()

    def _execute_tool_call(
        self,
        call: dict,
        tool_calls: list,
        outputs: list,
        index: int,
        has_terminating: bool,
    ) -> bool | None:
        """Refuse a withheld tool and park the turn on a delegate call."""
        if call['name'] in self._withheld_tool_names():
            self._record_tool_call(call)
            self._skip_tool_call(
                outputs,
                call,
                WITHHELD_SKIP_REASON,
                log_result={'error': 'tool_withheld'},
            )
            return False
        if call['name'] == DELEGATE_TOOL:
            return self._execute_delegate_call(
                call, tool_calls, outputs, index, has_terminating
            )
        return super()._execute_tool_call(
            call, tool_calls, outputs, index, has_terminating
        )

    def _record_tool_result(
        self,
        outputs: list,
        call_id: str,
        name: str,
        output_result,
        log_result=None,
        arguments: dict | None = None,
    ) -> None:
        """Fingerprint every real tool result of a subagent for loop detection."""
        super()._record_tool_result(
            outputs,
            call_id,
            name,
            output_result,
            log_result=log_result,
            arguments=arguments,
        )
        if self._is_child() and log_result is None:
            self._track_tool_fingerprint(outputs, name, arguments, output_result)

    def _process_tool_round(
        self,
        tool_calls: list,
        outputs: list,
        start_index: int,
        has_terminating: bool = False,
    ) -> bool | None:
        """End a subagent that made no progress once its round is recorded."""
        result = super()._process_tool_round(
            tool_calls, outputs, start_index, has_terminating=has_terminating
        )
        halt = (self.loop_state or {}).get('halt') if self._is_child() else None
        if halt and self.state == 'running':
            self.stop_reason = 'no_progress'
            self._transition_state('error', error=halt)
            return None
        return result

    @api.model
    def _rate_limit_domain(self) -> list:
        """Count the chats the user started, never the subagents they spawned."""
        return super()._rate_limit_domain() + [('parent_session_id', '=', False)]

    @api.model
    def _check_rate_limit(self, batch_size: int = 1) -> None:
        """Leave the subagents of a delegation out of the per-minute chat limit.

        :raise UserError: when the per-minute rate limit would be exceeded
        """
        if self.env.context.get('muk_ai_subagent_spawn'):
            return
        super()._check_rate_limit(batch_size)

    # ----------------------------------------------------------
    # Compute
    # ----------------------------------------------------------

    @api.depends('child_session_ids')
    def _compute_child_session_count(self) -> None:
        """Count the subagents each session spawned."""
        for record in self:
            record.child_session_count = len(record.child_session_ids)

    # ----------------------------------------------------------
    # Cron
    # ----------------------------------------------------------

    @api.model
    def _gc_sessions_older_than(self, days: int, domain: Domain) -> tuple[int, int]:
        """Keep subagents out of the retention sweep.

        A subagent is deleted with its run and never before it, or the
        parent's transcript names subagents that no longer exist.
        """
        return super()._gc_sessions_older_than(
            days, domain & Domain([('parent_session_id', '=', False)])
        )

    @api.model
    def _cron_sweep_stalled_children(self) -> None:
        """Stop every claimed subagent whose worker completed no round for too long.

        Only a claimed subagent counts, and both timestamps have to be old:
        the heartbeat is stamped before a provider round and the claim before
        every tool call, so one long round would look stalled on the
        heartbeat alone.
        """
        threshold = fields.Datetime.now() - timedelta(seconds=self._stall_seconds())
        stalled = self.sudo().search(
            [
                ('parent_session_id', '!=', False),
                ('state', '=', 'running'),
                ('claimed_at', '!=', False),
                ('claimed_at', '<', threshold),
                ('heartbeat_at', '<', threshold),
            ]
        )
        for child in stalled:
            child.with_user(child.user_id)._mark_stalled()
