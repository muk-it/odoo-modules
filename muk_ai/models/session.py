from __future__ import annotations

import logging
from collections.abc import Iterable

from odoo import Command, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.fields import Domain
from odoo.tools import SQL

from odoo.addons.muk_ai.tools.call import build_tool_call_output
from odoo.addons.muk_ai.tools.context import clean_view_context_payload
from odoo.addons.muk_ai.tools.conversation import (
    chat_title,
    is_counted_user_entry,
    open_call_ids,
    order_outputs,
)
from odoo.addons.muk_ai.tools.runtime import REASONING_EFFORT_SELECTION

_logger = logging.getLogger(__name__)

CONVERSATION_RESET = {'pending_ask': False, 'last_text': False, 'error_message': False}


class AISession(models.Model):
    """Stateful agent conversation: runtime, streaming, tools, and approvals."""

    _name = 'muk_ai.session'
    _inherit = [
        'muk_ai.session.prompt',
        'muk_ai.session.loop',
        'muk_ai.session.tool',
        'muk_ai.session.compact',
        'muk_ai.session.worker',
        'muk_ai.session.notify',
        'bus.listener.mixin',
    ]
    _description = 'AI Session'
    _explanation = (
        'A chat between a user and an AI agent: its messages, the tools the '
        'agent called, the state of the current turn, the tokens and cost it '
        'used, and who it is shared with. Use it to find, continue, hand over '
        'or review a chat.'
    )
    _order = 'create_date desc'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    name = fields.Char(
        string='Name',
        required=True,
        index=True,
    )

    user_named = fields.Boolean(
        string='Named by User',
        readonly=True,
        copy=False,
    )

    state = fields.Selection(
        selection=[
            ('new', 'New'),
            ('running', 'Running'),
            ('compacting', 'Compacting'),
            ('waiting', 'Waiting'),
            ('stopped', 'Stopped'),
            ('done', 'Done'),
            ('error', 'Error'),
        ],
        string='State',
        readonly=True,
        required=True,
        default='new',
        index=True,
        copy=False,
    )

    user_id = fields.Many2one(
        comodel_name='res.users',
        string='Owner',
        readonly=True,
        required=True,
        default=lambda self: self.env.user,
        index=True,
    )

    can_write = fields.Boolean(
        compute='_compute_can_write',
        string='Can Steer',
    )

    share_user_ids = fields.Many2many(
        comodel_name='res.users',
        relation='muk_ai_session_share_user_rel',
        column1='session_id',
        column2='user_id',
        string='Shared With',
        copy=False,
    )

    agent_id = fields.Many2one(
        comodel_name='muk_ai.agent',
        string='Agent',
        default=lambda self: self.env['muk_ai.agent']._get_default(),
        ondelete='set null',
    )

    space_id = fields.Many2one(
        comodel_name='muk_ai.space',
        string='Space',
        index=True,
        copy=False,
        ondelete='set null',
    )

    override_approval_mode = fields.Selection(
        selection=[
            ('ask', 'Ask on writes'),
            ('off', 'Never ask'),
        ],
        string='Approval Mode Override',
    )

    override_reasoning_effort = fields.Selection(
        selection=REASONING_EFFORT_SELECTION,
        string='Reasoning Effort Override',
    )

    conversation = fields.Json(
        string='Conversation',
        readonly=True,
        default=list,
        copy=False,
    )

    cleared_at = fields.Datetime(
        string='Cleared At',
        readonly=True,
        copy=False,
    )

    event_ids = fields.One2many(
        comodel_name='muk_ai.session.event',
        string='Events',
        readonly=True,
        inverse_name='session_id',
    )

    display_events = fields.Json(
        compute='_compute_display_events',
        string='Conversation Events',
    )

    log_ids = fields.One2many(
        comodel_name='muk_mcp.log',
        string='Tool Calls',
        readonly=True,
        inverse_name='session_id',
    )

    last_text = fields.Text(
        string='Last AI Message',
        readonly=True,
        copy=False,
    )

    view_context = fields.Json(
        string='View Context',
        readonly=True,
    )

    pending_ids = fields.One2many(
        comodel_name='muk_ai.session.pending',
        string='Pending Messages',
        readonly=True,
        inverse_name='session_id',
    )

    error_message = fields.Text(
        string='Error',
        readonly=True,
    )

    attachment_ids = fields.One2many(
        comodel_name='ir.attachment',
        inverse_name='res_id',
        domain=[('res_model', '=', 'muk_ai.session')],
        string='Attachments',
        copy=False,
        readonly=True,
    )

    _owner_recent_idx = models.Index('(user_id, create_date DESC)')

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _transition_state(
        self, state: str, error: str | None = None, values: dict | None = None
    ) -> None:
        """Persist a state with any further values and publish the state event.

        The write is flushed before it is announced. A waiting session also
        publishes what it waits on, a failed one its error.
        """
        self.write(
            {
                **(values or {}),
                'state': state,
                **({'error_message': error} if error else {}),
            }
        )
        self.flush_recordset()
        payload = {'state': state}
        if error:
            payload['error'] = error
        if state == 'waiting':
            payload['ask'] = self._public_pending_ask()
        self._publish_event('state', payload)

    def _extend_conversation(self, items: list[dict]) -> None:
        """Append items to the stored conversation."""
        self.conversation = [*(self.conversation or []), *(items or [])]

    def _close_orphan_tool_calls(
        self, result: dict, outputs: list | None = None
    ) -> None:
        """Append the given outputs and answer every call still open with ``result``.

        Images a round held back follow the outputs.
        """
        outputs = list(outputs or [])
        open_ids = open_call_ids([*(self.conversation or []), *outputs])
        outputs += [build_tool_call_output(call_id, result) for call_id in open_ids]
        if outputs:
            self._extend_conversation(
                self._flush_deferred_vision(order_outputs(outputs))
            )

    def _resolve_attachments(
        self, attachment_ids: Iterable[int] | None
    ) -> models.BaseModel:
        """Validate and bind requested attachments to this session.

        :raise UserError: when an attachment is missing or not accessible
        """
        requested = self.env['ir.attachment'].browse(
            [int(aid) for aid in attachment_ids or []]
        )
        attachments = requested.exists()
        new = attachments - self.attachment_ids
        if attachments != requested or new.filtered(
            lambda a: a.res_model and a.res_model != 'muk_ai.session'
        ):
            raise UserError(self.env._('One or more attachments could not be found.'))
        attachments._ai_validate()
        if new:
            new.check_access('write')
            new.sudo().write({'res_model': 'muk_ai.session', 'res_id': self.id})
            self.invalidate_recordset(['attachment_ids'])
        return attachments

    def _should_autoname(self) -> bool:
        """Return whether the first message of the conversation may retitle the chat.

        A chat starts with a placeholder and takes its title from what was
        asked, until somebody names it; a surface that opens a session under a
        name of its own overrides this.
        """
        return not self.user_named

    def _enrich_view_context(self, payload: dict) -> dict:
        """Return the view-context payload, optionally enriched by subclasses."""
        return payload

    def _write_view_context(self, payload: dict | None) -> None:
        """Persist the view context and broadcast its change."""
        if payload:
            payload = self._enrich_view_context(payload)
        self.write({'view_context': payload or False})
        self._publish_event('view_context', {'view_context': payload or None})

    def _resolve_event(self, event_id: int) -> models.BaseModel:
        """Return a session event by id, or raise when missing.

        :raise UserError: when the event is not part of this session
        """
        event = (
            self.env['muk_ai.session.event']
            .sudo()
            .search([('session_id', '=', self.id), ('id', '=', int(event_id))])
        )
        if not event:
            raise UserError(self.env._('Event not found in this session.'))
        return event

    def _conversation_cut_index(
        self, event: models.BaseModel, keep_turn: bool = False
    ) -> int:
        """Return the conversation index to cut at for an event.

        Mapped from the common tail of events and conversation, as a reset drops
        the conversation head. ``keep_turn`` keeps what the event produced (fork).
        """
        is_user = event.kind == 'user_message'
        later = (
            self.env['muk_ai.session.event']
            .sudo()
            .search_count(
                [
                    ('session_id', '=', self.id),
                    ('sequence', '>=' if is_user else '>', event.sequence),
                    ('kind', '=', 'user_message'),
                ]
            )
        )
        if is_user:
            rank, offset = later, 1 if keep_turn else 0
        else:
            rank, offset = (later, 0) if keep_turn else (later + 1, 1)
        conversation = list(self.conversation or [])
        if rank <= 0:
            return len(conversation)
        users = [
            index
            for index, item in enumerate(conversation)
            if is_counted_user_entry(item)
        ]
        return users[-rank] + offset if rank <= len(users) else 0

    def _snapshot_values(self) -> dict:
        """Return the record values a chat surface shows when it loads the session.

        Extension modules add the values of their own fields to the dict.
        """
        return {
            **self.read(['name', 'user_id', 'share_user_ids', 'agent_id'])[0],
            'tool_sources': self._tool_sources(),
        }

    def _announce_agent_switch(self, previous: models.BaseModel) -> None:
        """Mark a change of agent on the chat surfaces and in a started transcript."""
        agent = self.agent_id
        if self.event_ids:
            self._append_event(
                {
                    'kind': 'agent_switched',
                    'agent_name': agent.name or '',
                    'from_agent_name': previous.name or '',
                }
            )
        self._publish_event(
            'agent_switched',
            {
                'agent_id': agent.id,
                'agent_name': agent.name or '',
                'effective_approval_mode': self._effective_approval_mode(),
                'effective_reasoning_effort': self._effective_reasoning_effort()
                or False,
                'reasoning_effort_options': self._reasoning_effort_options(),
                'agent_reasoning_effort': agent.reasoning_effort or False,
                'tool_sources': self._tool_sources(),
            },
        )

    # ----------------------------------------------------------
    # Actions
    # ----------------------------------------------------------

    def action_open(self) -> dict:
        """Return the client action that opens this chat session.

        :raise AccessError: when the caller is not the session owner
        """
        self.ensure_one()
        if self.user_id != self.env.user:
            raise AccessError(
                self.env._('Only the session owner can continue this chat.')
            )
        return {
            'type': 'ir.actions.client',
            'tag': 'muk_ai.chat',
            'name': self.name or self.env._('AI Chat'),
            'params': {'session_id': self.id},
        }

    def action_stop(self) -> dict:
        """Stop the session, answering the tool calls a pause left open.

        :raise AccessError: when the caller is not the owner or an admin
        """
        self.ensure_one()
        if self.user_id != self.env.user and not self.env.is_admin():
            raise AccessError(
                self.env._(
                    'Only the session owner or an administrator can stop this session.'
                )
            )
        if self.state not in ('done', 'error', 'stopped'):
            if self.state == 'waiting':
                pending = self.pending_ask or {}
                results = pending.get('results') or {}
                self._close_orphan_tool_calls(
                    {'status': 'cancelled', 'reason': 'stopped_by_user'},
                    [
                        *(pending.get('outputs') or []),
                        *(build_tool_call_output(*item) for item in results.items()),
                    ],
                )
            self._transition_state('stopped', values={'pending_ask': False})
        return self.get_snapshot()

    def action_handover(self, new_user_id: int) -> bool:
        """Hand the chat over; it leaves its space and the giver stays a reader.

        :raise AccessError: when the caller is not the owner or an admin
        :raise UserError: when the session is busy or the target is invalid
        """
        self.ensure_one()
        if self.user_id != self.env.user and not self.env.is_admin():
            raise AccessError(
                self.env._(
                    'Only the session owner or an administrator can hand over this chat.'
                )
            )
        if self.state in ('running', 'compacting'):
            raise UserError(self.env._('Stop the session before handing it over.'))
        target = self.env['res.users'].sudo().browse(new_user_id).exists()
        if not target or target.share or not target.active:
            raise UserError(
                self.env._('Select an active internal user to hand over to.')
            )
        if target == self.user_id:
            return True
        old_owner, session = self.user_id, self.sudo()
        context = dict(session.user_context or {})
        companies = [
            company_id
            for company_id in context.get('allowed_company_ids') or []
            if company_id in target.company_ids.ids
        ]
        session.write(
            {
                'user_id': target.id,
                'space_id': False,
                'notification_unread': True,
                'approved_signatures': [],
                'share_user_ids': [
                    Command.link(old_owner.id),
                    Command.unlink(target.id),
                ],
                'user_context': {
                    **context,
                    **self.with_user(target).env['res.users'].context_get(),
                    'allowed_company_ids': companies or [target.company_id.id],
                },
            }
        )
        session.with_context(muk_ai_state_unchanged=True)._publish_event(
            'state', {'state': session.state}
        )
        session._post_notification(
            target,
            self.env._('Chat handed over to you'),
            self.env._(
                '%(name)s handed you the chat "%(chat)s".',
                name=old_owner.name,
                chat=session.name or '',
            ),
        )
        session._push_notification_badge(target)
        session._push_notification_badge(old_owner)
        return True

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    def fetch_events(
        self, limit: int = 100, before_sequence: int | None = None
    ) -> dict:
        """Return a window of the events the caller may see, newest last.

        Private lines of other users are left out.
        """
        self.check_access('read')
        domain = Domain('session_id', '=', self.id) & Domain(
            'private_user_id', 'in', [False, self.env.uid]
        )
        if before_sequence is not None:
            domain &= Domain('sequence', '<', before_sequence)
        rows = (
            self.env['muk_ai.session.event']
            .sudo()
            .search(domain, order='sequence desc, id desc', limit=limit + 1)
        )
        events = [
            {
                'kind': event.kind,
                **(event.payload or {}),
                'event_id': event.id,
                'sequence': event.sequence,
                'at': (event.payload or {}).get('at') or event.at.isoformat(),
            }
            for event in reversed(rows[:limit])
        ]
        return {
            'events': events,
            'has_more_older': len(rows) > limit,
            'oldest_sequence': events[0]['sequence'] if events else None,
        }

    def get_snapshot(self, include_conversation: bool = False) -> dict:
        """Return everything a chat surface needs to show the session."""
        snapshot = {
            **self._snapshot_values(),
            **self.fetch_events(limit=100),
            'error_message': self.error_message,
            'last_text': self.last_text,
            'attachments': [a._ai_describe() for a in self.attachment_ids],
            'total_input_cost': self.total_input_cost,
            'total_output_cost': self.total_output_cost,
            'pending_user_messages': self._serialize_pending(),
            'can_write': self.can_write,
            **self._state_metrics(),
        }
        if include_conversation:
            snapshot['conversation'] = self.conversation or []
        return snapshot

    def start(
        self,
        user_message: str | None = None,
        attachment_ids: list[int] | None = None,
    ) -> dict:
        """Start a session turn and trigger a worker.

        :raise AccessError: when the caller may only read the session
        :raise UserError: when the session is not in a startable state
        """
        self.check_access('write')
        self._recover_if_stuck()
        if self.state not in ('new', 'error', 'stopped'):
            raise UserError(self.env._('Session is not in a startable state.'))
        attachments = self._resolve_attachments(attachment_ids)
        if self.conversation:
            self._enqueue_user_turn(user_message, attachments)
        else:
            if self._should_autoname() and (title := chat_title(user_message)):
                self.write({'name': title, 'user_named': False})
                self._publish_event('rename', {'name': title})
            self.conversation = self._build_initial_inputs(user_message, attachments)
            self._enqueue_user_turn(user_message, attachments, extend=False)
        self._trigger_worker()
        return self.get_snapshot()

    def answer(self, answer: str, attachment_ids: list[int] | None = None) -> dict:
        """Answer a pending question and resume the turn.

        :raise AccessError: when the caller may only read the session
        :raise UserError: when the session is not awaiting an answer
        """
        self.check_access('write')
        self._recover_if_stuck()
        pending = self.pending_ask or {}
        if self.state != 'waiting' or pending.get('kind') != 'question':
            raise UserError(self.env._('Session is not waiting for user input.'))
        question = pending.get('text') or ''
        attachments = self._resolve_attachments(attachment_ids)
        if call_id := pending.get('call_id'):
            continuation = [
                build_tool_call_output(
                    call_id,
                    {'status': 'answered', 'question': question, 'answer': answer},
                )
            ]
            entry = self._build_user_entry(None, attachments)
        else:
            continuation = []
            text = f'Answer to "{question}": {answer}' if question else answer
            entry = self._build_user_entry(text, attachments)
        if entry:
            continuation.append({**entry, '_answer_entry': True})
        self._resume_turn(
            continuation,
            {
                'kind': 'answer',
                'question': question,
                'answer': answer,
                'attachments': [a._ai_describe() for a in attachments],
            },
        )
        return self.get_snapshot()

    def send_message(
        self, user_message: str, attachment_ids: list[int] | None = None
    ) -> dict:
        """Route a user message to start, answer, queue, or extend a turn."""
        self.check_access('write')
        self._recover_if_stuck()
        waiting = self.state == 'waiting'
        if self.state in ('running', 'compacting') or (
            waiting and self._pending_ask_queues_input()
        ):
            return self.enqueue_message(user_message, attachment_ids=attachment_ids)
        if waiting and (self.pending_ask or {}).get('kind') == 'question':
            return self.answer(user_message, attachment_ids=attachment_ids)
        if not self.conversation:
            return self.start(user_message, attachment_ids=attachment_ids)
        attachments = self._resolve_attachments(attachment_ids)
        self._enqueue_user_turn(user_message, attachments)
        self._trigger_worker()
        return self.get_snapshot()

    def enqueue_message(
        self, user_message: str | None, attachment_ids: list[int] | None = None
    ) -> dict:
        """Queue a user message and return the session snapshot.

        A settled session queues nothing; its snapshot carries ``queue_rejected_state``.

        :raise AccessError: when the caller may only read the session
        """
        self.ensure_one()
        self.check_access('write')
        self.flush_recordset()
        self.env.cr.execute(
            SQL('SELECT state FROM muk_ai_session WHERE id = %s FOR UPDATE', self.id)
        )
        state = self.env.cr.fetchone()[0]
        self.invalidate_recordset(['state'])
        if state not in ('running', 'waiting', 'compacting'):
            return {**self.get_snapshot(), 'queue_rejected_state': state}
        self.env['muk_ai.session.pending'].create(
            {
                'session_id': self.id,
                'content': user_message or '',
                'attachment_ids': list(attachment_ids or []),
            }
        )
        self.invalidate_recordset(['pending_ids'])
        self._publish_event('queue', {'pending': self._serialize_pending()})
        return self.get_snapshot()

    def cancel_queued(self, index: int) -> dict:
        """Remove a queued message by index and return the snapshot.

        :raise AccessError: when the caller may only read this chat
        """
        self.check_access('write')
        if 0 <= index < len(pending := self.pending_ids):
            pending[index].unlink()
            self.invalidate_recordset(['pending_ids'])
            self._publish_event('queue', {'pending': self._serialize_pending()})
        return self.get_snapshot()

    def regenerate_last_turn(self) -> dict:
        """Rewind to the last user turn and re-run it.

        :raise AccessError: when the caller may only read the session
        :raise UserError: when running, compacting, waiting, or no user turn exists
        """
        self.check_access('write')
        if self.state in ('running', 'compacting', 'waiting'):
            raise UserError(
                self.env._(
                    'Cannot regenerate while the session is running, compacting, or waiting.'
                )
            )
        conversation = list(self.conversation or [])
        users = [
            index
            for index, item in enumerate(conversation)
            if is_counted_user_entry(item)
        ]
        if not users:
            raise UserError(self.env._('No user turn to regenerate from.'))
        self.conversation = conversation[: users[-1] + 1]
        events = self.env['muk_ai.session.event'].sudo()
        last = events.search(
            [('session_id', '=', self.id), ('kind', '=', 'user_message')],
            order='sequence desc',
            limit=1,
        )
        events.search(
            [
                ('session_id', '=', self.id),
                ('sequence', '>', last.sequence if last else -1),
            ]
        ).unlink()
        self._transition_state(
            'running', values={'pending_ask': False, **self._turn_start_values()}
        )
        self._trigger_worker()
        return self.get_snapshot()

    def clear(self) -> dict:
        """Reset the conversation and session state to new.

        :raise AccessError: when the caller may only read the session
        :raise UserError: when the session is running or compacting
        """
        self.check_access('write')
        if self.state in ('running', 'compacting'):
            raise UserError(
                self.env._(
                    'Cannot clear the conversation while the session is running.'
                )
            )
        self.pending_ids.unlink()
        self.invalidate_recordset(['pending_ids'])
        self._append_event(
            {
                'kind': 'command',
                'name': '/clear',
                'message': self.env._('Context cleared.'),
            }
        )
        self._transition_state(
            'new',
            values={
                **CONVERSATION_RESET,
                'conversation': [],
                'approved_signatures': [],
                'iteration_count': 0,
                'last_input_tokens': 0,
                'turn_usage': False,
                'cleared_at': fields.Datetime.now(),
            },
        )
        self._publish_event('queue', {'pending': []})
        return self.get_snapshot()

    def compact(self) -> dict:
        """Begin asynchronous conversation compaction.

        :raise AccessError: when the caller may only read the session
        :raise UserError: when running, waiting, or the conversation is empty
        """
        self.check_access('write')
        if self.state in ('running', 'compacting'):
            raise UserError(
                self.env._('Cannot compact while the session is running. Stop first.')
            )
        if self.state == 'waiting':
            raise UserError(
                self.env._(
                    'Cannot compact while the session is waiting for user input.'
                )
            )
        if not self.conversation:
            raise UserError(
                self.env._('Nothing to compact yet - the conversation is empty.')
            )
        self._begin_compact_progress()
        self._transition_state('compacting', values={'error_message': False})
        self._trigger_worker()
        return self.get_snapshot()

    def stop_compact(self) -> dict:
        """Cancel an in-progress compaction and return to done."""
        self.check_access('write')
        if self.state != 'compacting':
            return self.get_snapshot()
        event = self._compact_events(1)
        if (event.payload or {}).get('state') == 'streaming':
            self._patch_compact_progress(
                event,
                {
                    'state': 'cancelled',
                    'message': self.env._('Compaction cancelled by user.'),
                },
            )
        self._transition_state('done', values={'error_message': False})
        return self.get_snapshot()

    def undo_to_event(self, event_id: int) -> dict:
        """Rewind the conversation and events back to before an event.

        :raise AccessError: when the caller may only read the session
        :raise UserError: when the session is running, compacting, or waiting
        """
        self.check_access('write')
        if self.state in ('running', 'compacting'):
            raise UserError(self.env._('Cannot rewind while the session is running.'))
        if self.state == 'waiting':
            raise UserError(
                self.env._('Cannot rewind while the session is waiting for input.')
            )
        target = self._resolve_event(event_id)
        cut = self._conversation_cut_index(target)
        conversation = list(self.conversation or [])[:cut]
        self.env['muk_ai.session.event'].sudo().search(
            [('session_id', '=', self.id), ('sequence', '>=', target.sequence)]
        ).unlink()
        self._transition_state(
            'done' if conversation else 'new',
            values={**CONVERSATION_RESET, 'conversation': conversation},
        )
        return self.get_snapshot()

    def fork_at_event(self, event_id: int) -> int:
        """Fork a new session copied up to the given event; return its id.

        :raise AccessError: when the caller may only read the session
        :raise UserError: when the session is running or compacting
        """
        self.check_access('write')
        if self.state in ('running', 'compacting'):
            raise UserError(self.env._('Cannot fork while the session is running.'))
        target = self._resolve_event(event_id)
        cut = self._conversation_cut_index(target, keep_turn=True)
        conversation = list(self.conversation or [])[:cut]
        fork = self.copy(
            {
                **CONVERSATION_RESET,
                'name': self.env._('%s (fork)', self.name),
                'conversation': conversation,
                'state': 'done' if conversation else 'new',
                'iteration_count': 0,
            }
        )
        self.env['muk_ai.session.event'].sudo().search(
            [('session_id', '=', self.id), ('sequence', '<=', target.sequence)],
            order='sequence, id',
        ).copy({'session_id': fork.id})
        return fork.id

    def upload_attachments(self, files: list[dict] | None) -> list[dict]:
        """Create session attachments from uploads and return descriptors."""
        self.check_access('write')
        created = self.env['ir.attachment']
        for entry in files or []:
            created |= created.sudo()._ai_create_from_upload(
                entry.get('filename'),
                entry.get('mimetype'),
                entry.get('data_b64'),
                res_id=self.id,
            )
        if created:
            self.invalidate_recordset(['attachment_ids'])
        return [a._ai_describe() for a in created]

    def discard_attachments(self, attachment_ids: list[int] | None) -> bool:
        """Unlink the named attachments owned by this session."""
        self.check_access('write')
        ids = {int(aid) for aid in attachment_ids or []}
        if owned := self.attachment_ids.filtered(lambda a: a.id in ids):
            owned.sudo().unlink()
            self.invalidate_recordset(['attachment_ids'])
        return True

    def set_view_context(self, payload: dict | None) -> dict:
        """Pin or clear the session's view context from a client payload."""
        self.check_access('write')
        kind = payload.get('kind') if isinstance(payload, dict) else None
        self._write_view_context(
            None
            if payload is None or kind == 'none'
            else clean_view_context_payload(kind, payload)
        )
        return self.get_snapshot()

    def unpin_view_context(self) -> dict:
        """Clear the pinned view context and record the command."""
        self.check_access('write')
        self._write_view_context(None)
        self._append_event(
            {
                'kind': 'command',
                'name': '/unpin',
                'message': self.env._('View context cleared.'),
            }
        )
        return self.get_snapshot()

    def set_approval_mode(self, mode: str | None) -> dict:
        """Override the session approval mode.

        :raise AccessError: when the caller may only read the session
        :raise UserError: when the mode is not ``ask`` or ``off``
        """
        self.check_access('write')
        if mode and mode not in ('ask', 'off'):
            raise UserError(self.env._('Unknown approval mode %(mode)r.', mode=mode))
        self.write({'override_approval_mode': mode or False})
        self._publish_event('state', {'state': self.state})
        return self.get_snapshot()

    def set_tool_source(self, key: str, enabled: bool) -> dict:
        """Switch a tool source of this chat on or off.

        :raise AccessError: when the caller may only read the session
        :raise UserError: when the chat has no tool source ``key``
        """
        self.check_access('write')
        if key not in {source['key'] for source in self._tool_sources()}:
            raise UserError(self.env._('Unknown tool source %(key)r.', key=key))
        disabled = set(self.disabled_tool_sources or []) - {key}
        self.disabled_tool_sources = sorted(disabled if enabled else disabled | {key})
        return self.get_snapshot()

    def set_reasoning_effort(self, effort: str | None) -> dict:
        """Override the effort tier the session's turns run on.

        :raise AccessError: when the caller may only read the session
        :raise UserError: when the tier is not one the chat model accepts
        """
        self.check_access('write')
        if effort and effort not in self._reasoning_effort_options():
            raise UserError(
                self.env._('Unknown reasoning effort %(effort)r.', effort=effort)
            )
        self.write({'override_reasoning_effort': effort or False})
        self._publish_event('state', {'state': self.state})
        return self.get_snapshot()

    def approve_tool(self) -> dict:
        """Approve the pending tool call once and resume the round."""
        return self._decide_tool('approved')

    def approve_for_session(self) -> dict:
        """Approve the pending call and allow its signature for the session."""
        return self._decide_tool('approved_session')

    def reject_tool(self, reason: str | None = None) -> dict:
        """Reject the pending tool call and resume the round with the rejection."""
        reason = (reason or '').strip() or self.env._('User rejected the call.')
        return self._decide_tool('rejected', reason)

    def submit_client_result(self, call_id: str, result) -> dict:
        """Submit a client-executed tool result, resuming once all are in.

        :raise AccessError: when the caller may only read the session
        :raise UserError: when the session is busy or not awaiting this
            client action
        """
        self.check_access('write')
        with self._session_lock():
            pending = self._require_pending_client_action(call_id)
            self._apply_client_result(pending, call_id, result)
        return self.get_snapshot()

    def reject_client_action(
        self, call_id: str | None = None, reason: str | None = None
    ) -> dict:
        """Reject one or all pending client actions with an error result.

        Without ``call_id`` every unanswered action is rejected and the turn resumes.

        :raise UserError: when the session is busy or not awaiting this action
        """
        self.check_access('write')
        result = {'error': 'rejected', 'reason': reason or ''}
        with self._session_lock():
            pending = self._require_pending_client_action(call_id)
            results = pending.get('results') or {}
            call_ids = (
                [call_id]
                if call_id is not None
                else [
                    action['call_id']
                    for action in pending.get('actions') or []
                    if action.get('call_id') not in results
                ]
            )
            for action_id in call_ids:
                self._apply_client_result(pending, action_id, result)
        return self.get_snapshot()

    # ----------------------------------------------------------
    # Compute
    # ----------------------------------------------------------

    @api.depends_context('uid', 'su')
    def _compute_can_write(self) -> None:
        """Say whether this user may steer each chat, not merely read it.

        Asked of the record rules rather than inferred from ownership: a chat
        can be writable without being owned, and the client must not guess.
        """
        allowed = self._filtered_access('write')
        for record in self:
            record.can_write = record in allowed

    @api.depends('event_ids', 'event_ids.sequence', 'event_ids.payload')
    def _compute_display_events(self) -> None:
        """Load the most recent events for display."""
        for record in self:
            record.display_events = (
                record.fetch_events(limit=100)['events'] if record.id else []
            )

    # ----------------------------------------------------------
    # Constraints
    # ----------------------------------------------------------

    @api.constrains('space_id', 'user_id')
    def _check_space_owner(self) -> None:
        """Allow filing a chat only into a personal space of its owner."""
        for record in self.filtered('space_id'):
            space = record.space_id.sudo()
            if space.domain:
                raise ValidationError(
                    self.env._(
                        'Chats cannot be filed into the system space "%s".', space.name
                    )
                )
            if space.user_id != record.user_id:
                raise ValidationError(
                    self.env._('The space "%s" belongs to another user.', space.name)
                )

    # ----------------------------------------------------------
    # ORM
    # ----------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list: list[dict]) -> AISession:
        """Enforce the rate limit and broadcast the new chats to their owners."""
        self._check_rate_limit(batch_size=len(vals_list) or 1)
        records = super().create(vals_list)
        for record in records:
            record._audience_users()._bus_send(
                'muk_ai.session_state', record._list_payload()
            )
        return records

    def write(self, vals: dict) -> bool:
        """Mark agent switches, share changes and names a user chose.

        Filing an unread chat also refreshes the badge, and changing who a chat
        is shared with tells the people it was given to or taken from.
        """
        if 'name' in vals and 'user_named' not in vals:
            vals = {**vals, 'user_named': True}
        agents = {r.id: r.agent_id for r in self} if 'agent_id' in vals else None
        shared = (
            {r.id: r.share_user_ids for r in self} if 'share_user_ids' in vals else None
        )
        owners = (
            self.filtered('notification_unread').user_id
            if 'space_id' in vals
            else self.env['res.users']
        )
        result = super().write(vals)
        for owner in owners:
            self._push_notification_badge(owner)
        for record in self:
            if shared is not None:
                record._notify_share_change(shared[record.id])
            if agents is not None and agents[record.id] != record.agent_id:
                record._announce_agent_switch(agents[record.id])
        return result

    def unlink(self) -> bool:
        """Broadcast deletions so open chat surfaces drop the session live."""
        users = self.user_id
        for record in self:
            record._audience_users()._bus_send(
                'muk_ai.session_state', {'session_id': record.id, 'deleted': True}
            )
        result = super().unlink()
        for user in users:
            self._push_notification_badge(user)
        return result

    # ----------------------------------------------------------
    # Cron
    # ----------------------------------------------------------

    @api.autovacuum
    def _gc_sessions(self) -> tuple[int, int]:
        """Delete the finished chats nobody asked to keep.

        Spaces with a retention sweep their own chats, the rest follow the setting.

        :return: how many chats were deleted, and how many are still due
        """
        spaces = (
            self.env['muk_ai.space']
            .sudo()
            .search([('retention_mode', '!=', 'default')])
        )
        kept = Domain.FALSE
        for space in spaces.filtered(lambda space: space.retention_mode == 'forever'):
            kept |= Domain(space._session_domain())
        general = ~kept
        done = remaining = 0
        for space in spaces.filtered(lambda space: space.retention_mode == 'days'):
            claimed = Domain(space._session_domain())
            swept, due = self._gc_sessions_older_than(
                space.retention_days, claimed & ~kept
            )
            done, remaining = done + swept, remaining + due
            general &= ~claimed
        swept, due = self._gc_sessions_older_than(self._retention_days(), general)
        done, remaining = done + swept, remaining + due
        if done:
            _logger.info('Retention deleted %s chats, %s still due.', done, remaining)
        return done, remaining
