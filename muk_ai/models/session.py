import base64
import json
import random
import re
import time

from contextlib import suppress
from datetime import timedelta

import psycopg2
import urllib3

from markupsafe import Markup, escape

from odoo import SUPERUSER_ID, _, api, fields, models, modules, release
from odoo.exceptions import AccessError, UserError
from odoo.tools import SQL
from odoo.service.model import (
    MAX_TRIES_ON_CONCURRENCY_FAILURE,
    PG_CONCURRENCY_EXCEPTIONS_TO_RETRY,
)

from odoo.addons.muk_ai.tools import (
    ADVISORY_LOCK_NAMESPACE,
    ALLOWED_MIMETYPES,
    ASK_USER_TOOL,
    ATTACHMENT_REF_MAX_BYTES,
    ATTACHMENT_REF_RE,
    COMPACT_AUTO_RATIO,
    COMPACT_SUMMARY_REINJECTION,
    COMPACT_SUMMARY_SYSTEM,
    COMPACT_SUMMARY_TEMPLATE,
    DEFAULT_CONTEXT_WINDOW,
    INLINE_IMAGE_RE,
    MAX_ITERATIONS,
    MAX_TOOL_CALLS_PER_ROUND,
    MAX_WALLCLOCK_SECONDS,
    TERMINATING_TOOLS,
    TOOL_LOAD_TOOL,
    URL_REF_RE,
    WORKER_HEARTBEAT_INTERVAL,
    WORKER_STALE_THRESHOLD,
    StreamCancelled,
    build_tool_call_output,
    clean_view_context_payload,
    fetch_url,
    sanitize_json_schema,
    with_ui_ctx,
)


class AISession(models.Model):

    _name = 'muk_ai.session'
    _inherit = ['bus.listener.mixin']
    _description = "AI Session"
    _order = 'create_date desc'

    # ----------------------------------------------------------
    # Fields Identity
    # ----------------------------------------------------------

    name = fields.Char(
        string="Name",
        required=True,
        index=True,
    )

    state = fields.Selection(
        selection=[
            ('new', "New"),
            ('running', "Running"),
            ('compacting', "Compacting"),
            ('waiting', "Waiting"),
            ('stopped', "Stopped"),
            ('done', "Done"),
            ('error', "Error"),
        ],
        string="State",
        readonly=True,
        required=True,
        default='new',
        index=True,
        copy=False,
    )

    claimed_at = fields.Datetime(
        string="Worker Claimed At",
        help=(
            "Heartbeat written by the cron worker while processing this "
            "session. Sessions in `running` or `compacting` state with a "
            "stale heartbeat are reclaimed as orphans by the next cron tick."
        ),
        readonly=True,
        index=True,
        copy=False,
    )

    user_context = fields.Json(
        string="User Context",
        help=(
            "Snapshot of the calling user's environment context captured at "
            "trigger time. Restored by the cron worker so tools see the same "
            "language, timezone, and allowed companies as the originating "
            "request."
        ),
        readonly=True,
        copy=False,
    )

    user_id = fields.Many2one(
        comodel_name='res.users',
        string="Owner",
        readonly=True,
        required=True,
        default=lambda self: self.env.user,
        index=True,
    )

    # ----------------------------------------------------------
    # Fields Configuration
    # ----------------------------------------------------------

    agent_id = fields.Many2one(
        comodel_name='muk_ai.agent',
        string="Agent",
        default=lambda self: self.env['muk_ai.agent']._get_default(),
        ondelete='set null',
    )

    override_approval_mode = fields.Selection(
        selection=[
            ('ask', "Ask on writes"),
            ('off', "Never ask"),
        ],
        string="Approval Mode Override",
        help=(
            "Per-session override for the agent's approval policy. "
            "Leave empty to inherit from the agent."
        ),
    )

    effective_approval_mode = fields.Char(
        compute='_compute_effective_approval_mode',
        string="Effective Approval Mode",
    )

    # ----------------------------------------------------------
    # Fields State
    # ----------------------------------------------------------

    conversation = fields.Json(
        string="Conversation",
        readonly=True,
        default=list,
    )

    cleared_at = fields.Datetime(
        string="Cleared At",
        help="Wall-clock marker set by /clear and /compact.",
        readonly=True,
        copy=False,
    )

    event_ids = fields.One2many(
        comodel_name='muk_ai.session.event',
        string="Events",
        readonly=True,
        inverse_name='session_id',
    )

    display_events = fields.Json(
        compute='_compute_display_events',
        string="Conversation Events",
        help=(
            "Flat list of session events in the shape consumed by the "
            "chat-style events widget. Mirrors `fetch_events()['events']`."
        ),
    )

    log_ids = fields.One2many(
        comodel_name='muk_mcp.log',
        string="Tool Calls",
        readonly=True,
        inverse_name='session_id',
    )

    last_text = fields.Text(
        string="Last AI Message",
        readonly=True,
    )

    view_context = fields.Json(
        string="View Context",
        help=(
            "Sticky description of the Odoo view the user is looking at. "
            "Injected as a <ui_ctx> tag on every provider request until it "
            "is replaced by a navigation tool result or cleared via /unpin."
        ),
        readonly=True,
    )

    pending_ask = fields.Json(
        string="Pending Ask",
        help=(
            "What the session is paused on: a free-text question from "
            "ask_user (`kind: 'question'`) or a risky tool call awaiting "
            "explicit confirmation (`kind: 'approval'`). The UI reads this "
            "to render the pending ask card; the resume path depends on "
            "`kind`."
        ),
        readonly=True,
    )

    approved_signatures = fields.Json(
        string="Approved Signatures",
        help=(
            "Risk signatures the user has approved for this conversation. "
            "A signature in this list bypasses the approval gate on the "
            "next matching tool call. Scope is this session only."
        ),
        readonly=True,
    )

    pending_ids = fields.One2many(
        comodel_name='muk_ai.session.pending',
        string="Pending Messages",
        help=(
            "FIFO queue of user messages typed while the session was busy. "
            "Drained as one combined turn at the end of `_run_to_completion`."
        ),
        readonly=True,
        inverse_name='session_id',
    )

    expanded_tool_names = fields.Json(
        string="Loaded Tools",
        help=(
            "Tool names whose full schemas have been loaded into this "
            "session via tool_load. Append-only within a session. "
            "Essentials and meta-tools (tool_load, ask_user) are always "
            "loaded regardless of this list."
        ),
        readonly=True,
        default=list,
    )

    pending_user_messages = fields.Json(
        compute='_compute_pending_user_messages',
        string="Queued User Messages",
        help=(
            "Serialized snapshot of `pending_ids` in the shape consumed by "
            "the chat client."
        ),
    )

    error_message = fields.Text(
        string="Error",
        readonly=True,
    )

    attachment_ids = fields.Many2many(
        comodel_name='ir.attachment',
        relation='muk_ai_session_ir_attachment_rel',
        column1='session_id',
        column2='attachment_id',
        string="Attachments",
        readonly=True,
    )

    # ----------------------------------------------------------
    # Fields Usage
    # ----------------------------------------------------------

    iteration_count = fields.Integer(
        string="Iterations",
        readonly=True,
        default=0,
    )

    total_input_tokens = fields.Integer(
        string="Input Tokens",
        readonly=True,
        default=0,
    )

    total_output_tokens = fields.Integer(
        string="Output Tokens",
        readonly=True,
        default=0,
    )

    total_input_cost = fields.Float(
        string="Input Cost (USD)",
        help=(
            "Cumulative USD spent on input tokens for this session. "
            "Frozen at accrual time against the model record that was "
            "active; later pricing edits do not rewrite history."
        ),
        readonly=True,
        default=0.0,
        digits=(12, 6),
    )

    total_output_cost = fields.Float(
        string="Output Cost (USD)",
        help="Cumulative USD spent on output tokens for this session.",
        readonly=True,
        default=0.0,
        digits=(12, 6),
    )

    total_cost = fields.Float(
        string="Total Cost (USD)",
        help="Cumulative USD for this session (input + output).",
        readonly=True,
        default=0.0,
        digits=(12, 6),
    )

    last_input_tokens = fields.Integer(
        string="Last Input Tokens",
        help=(
            "Input tokens consumed by the most recent provider round. "
            "Drives the context-window usage meter."
        ),
        readonly=True,
        default=0,
    )

    context_window = fields.Integer(
        compute='_compute_context_window',
        string="Context Window",
        help="Effective context window size for the session's active model.",
    )

    # ----------------------------------------------------------
    # Helper Resolvers
    # ----------------------------------------------------------

    @api.model
    def _get_terminating_tools(self):
        return TERMINATING_TOOLS

    @api.model
    def _get_system_prompt(self):
        return self.env['muk_ai.agent']._get_default().system_prompt

    def _effective_system_prompt(self):
        raw = (
            self.agent_id.system_prompt
            if self.agent_id and self.agent_id.system_prompt
            else self._get_system_prompt()
        )
        return self._render_system_prompt(raw or '')

    def _build_available_tools_block(self):
        catalog_names = {
            entry['name']
            for entry in self._get_filtered_catalog()
            if entry.get('name')
        }
        loaded = set(self._loaded_tool_names()) & catalog_names
        if deferred := sorted(catalog_names - loaded):
            lines = [
                '<available_tools>',
                (
                    'This list is COMPLETE: every tool the session can call '
                    'is either in your `tools` array (immediately callable) '
                    'or listed below by name. Do NOT call list_models or any '
                    'other tool to look for tools — every name is here.'
                ),
                (
                    'To use a tool listed below, call tool_load with a '
                    '`call` argument that loads the schema AND executes the '
                    'tool in ONE round-trip:'
                ),
                'tool_load(names=["<tool>"], call={name: "<tool>", arguments: {...}})',
                (
                    'Returns {loaded: {...}, call: {output: <result>}}. No '
                    'follow-up turn. This is the strongly preferred shape '
                    'for any deferred tool — never load and then call in '
                    'two separate rounds when one will do.'
                ),
                *self._available_tools_extra_paragraphs(),
                ', '.join(deferred),
                '</available_tools>',
            ]
            return '\n'.join(lines)
        return ''

    def _available_tools_extra_paragraphs(self):
        return []

    def _session_prompt_extras(self):
        return {
            'approval_mode': (
                self._effective_approval_mode()
                if self and self.id else 'ask'
            ),
        }

    def _render_system_prompt(self, raw):
        agent = self.agent_id or self.env['muk_ai.agent']._get_default()
        return agent._render_prompt(raw, **self._session_prompt_extras())

    def _build_runtime_block(self):
        lines = [
            '<runtime>',
            'Facts about this session. Use them directly; do not look them up.',
            f'Odoo: {release.version}',
            f'Date: {fields.Date.context_today(self).isoformat()}',
            f'User: {self.env.user.name} (res.users,{self.env.user.id}) — tz {self.env.user.tz or "UTC"}',
            f'Company: {self.env.company.name} (res.company,{self.env.company.id})',
            f'Approval mode: {self._effective_approval_mode() if self and self.id else "ask"}',
        ]
        if len(self.env.user.company_ids) > 1:
            names = ', '.join(self.env.user.company_ids.sorted('id').mapped('name'))
            lines.append(f'Companies accessible: {names}')
        lines.append('</runtime>')
        return '\n'.join(lines)

    def _effective_model_record(self):
        if self.agent_id and self.agent_id.model_id:
            return self.agent_id.model_id
        return self.env['muk_ai.provider']._get_default().default_model_id

    def _effective_provider(self):
        if record := self._effective_model_record():
            return record.provider_id
        return self.env['muk_ai.provider']._get_default()

    def _effective_model(self):
        if record := self._effective_model_record():
            return record.technical_name
        return None

    def _resolve_context_window(self):
        record = self._effective_model_record()
        return (
            (record.context_window if record else 0) or
            DEFAULT_CONTEXT_WINDOW
        )

    def _effective_approval_mode(self):
        if self.override_approval_mode:
            return self.override_approval_mode
        if self.agent_id and self.agent_id.approval_mode:
            return self.agent_id.approval_mode
        return 'ask'

    # ----------------------------------------------------------
    # Helper Inputs
    # ----------------------------------------------------------

    @staticmethod
    def _tool_entry_to_schema(entry):
        schema = (
            entry.get('inputSchema') or
            {'type': 'object', 'properties': {}}
        )
        return {
            'type': 'function',
            'name': entry['name'],
            'description': entry.get('description') or '',
            'parameters': sanitize_json_schema(schema),
            'strict': False,
        }

    def _build_user_entry(self, user_message=None, attachments=None):
        content = []
        if user_message:
            content.append({'type': 'input_text', 'text': user_message})
        for attachment in attachments or []:
            content.append({
                'type': 'muk_ai_attachment',
                'attachment_id': attachment.id,
                'filename': attachment.name,
                'mimetype': attachment.mimetype,
            })
        return {'role': 'user', 'content': content} if content else None

    def _build_initial_inputs(self, user_message=None, attachments=None):
        parts = [
            self._effective_system_prompt(),
            self._build_runtime_block(),
            self._build_available_tools_block(),
        ]
        inputs = [{
            'role': 'system',
            'content': [{
                'type': 'input_text',
                'text': '\n\n'.join(part for part in parts if part),
            }],
        }]
        if user_entry := self._build_user_entry(user_message, attachments):
            inputs.append(user_entry)
        return inputs

    def _user_message_log(self, user_message, attachments):
        return {
            'kind': 'user_message',
            'content': user_message or '',
            'attachments': [a._ai_describe() for a in attachments],
        }

    def _get_filtered_catalog(self):
        tool_env = self.env(context={**self.env.context, **self._tool_dispatch_context()})
        catalog = list(tool_env['muk_mcp.tool'].sudo().get_tools(registry='odoo'))
        if self.agent_id:
            catalog = self.agent_id.apply_tool_filter(catalog)
        return catalog

    def _get_essential_tool_names(self):
        if self.agent_id:
            return self.agent_id._get_essential_tool_names()
        return self.env['muk_ai.agent']._get_default_essential_tool_names()

    def _loaded_tool_names(self):
        seen, result = set(), []
        for name in self._get_essential_tool_names() + list(self.expanded_tool_names or []):
            if name and name not in seen:
                seen.add(name)
                result.append(name)
        return result

    def _get_tool_schema(self):
        catalog_by_name = {entry['name']: entry for entry in self._get_filtered_catalog()}
        loaded = set(self._loaded_tool_names()) & set(catalog_by_name)
        result = [
            self._tool_entry_to_schema(catalog_by_name[name])
            for name in sorted(loaded)
        ]
        if set(catalog_by_name) - loaded:
            result.append(self._tool_entry_to_schema(TOOL_LOAD_TOOL))
        if self._effective_approval_mode() != 'off' and 'ask_user' not in loaded:
            result.append(self._tool_entry_to_schema(ASK_USER_TOOL))
        return result

    def _build_request_inputs(self):
        return with_ui_ctx(self.conversation, self.view_context)

    # ----------------------------------------------------------
    # Helper Bus
    # ----------------------------------------------------------

    def _bus_channel(self):
        return self.user_id.partner_id

    def _state_metrics(self):
        return {
            'state': self.state,
            'iteration_count': self.iteration_count,
            'total_input_tokens': self.total_input_tokens,
            'total_output_tokens': self.total_output_tokens,
            'last_input_tokens': self.last_input_tokens,
            'context_window': self._resolve_context_window(),
            'view_context': self.view_context or None,
            'pending_ask': self.pending_ask or None,
            'override_approval_mode': self.override_approval_mode or False,
            'effective_approval_mode': self._effective_approval_mode(),
            'total_cost': self.total_cost,
        }

    def _publish_event(self, event_type, payload):
        self._bus_send('muk_ai.event', {
            'session_id': self.id,
            'type': event_type,
            'payload': payload,
        })
        if event_type == 'state':
            self._bus_send('muk_ai.session_state', {
                'session_id': self.id,
                'name': self.name,
                **self._state_metrics(),
            })
            self._notify_state_transition(payload)
        elif event_type == 'rename':
            self._bus_send('muk_ai.session_state', {
                'session_id': self.id,
                'name': self.name,
                'state': self.state,
            })

    def _notify_state_transition(self, payload):
        new_state = (payload or {}).get('state')
        if new_state in ('done', 'waiting', 'error'):
            ask = (payload or {}).get('ask') or self.pending_ask or {}
            ask_kind = ask.get('kind') if isinstance(ask, dict) else None
            title, message = self._notification_summary(new_state, payload, ask_kind)
            with suppress(Exception):
                self._bus_send('muk_ai.session_notification', {
                    'session_id': self.id,
                    'session_name': self.name,
                    'state': new_state,
                    'ask_kind': ask_kind,
                    'title': title,
                    'message': message,
                })
            if new_state == 'waiting':
                self._post_inbox_notification(title, message)

    def _notification_summary(self, new_state, payload, ask_kind):
        name = self.name or _("AI Session")
        if new_state == 'done':
            return (
                _("AI session finished"),
                _("Session “%(name)s” has finished.", name=name),
            )
        if new_state == 'error':
            raw = (payload or {}).get('error') or self.error_message
            return (
                _("AI session error"),
                _(
                    "Session “%(name)s” stopped: %(reason)s",
                    name=name,
                    reason=self._short_error_reason(raw) if raw else _("unknown error"),
                ),
            )
        if ask_kind == 'approval':
            return (
                _("AI session needs approval"),
                _(
                    "Session “%(name)s” is waiting for your approval before "
                    "running a tool.",
                    name=name,
                ),
            )
        return (
            _("AI session needs your input"),
            _("Session “%(name)s” is waiting for your answer.", name=name),
        )

    def _short_error_reason(self, raw):
        text = raw.strip()[:8192]
        if match := re.search(r'\{.*\}', text, flags=re.DOTALL):
            try:
                data = json.loads(match.group(0))
                error = (
                    data.get('error')
                    if isinstance(data, dict)
                    else None
                )
                if isinstance(error, dict) and error.get('message'):
                    text = error['message']
                elif data.get('message'):
                    text = data['message']
            except (ValueError, AttributeError):
                pass
        text = ' '.join(text.split())
        return text[:197] + '…' if len(text) > 200 else text

    def _post_inbox_notification(self, title, message):
        if partner := self.user_id.partner_id:
            body = (
                Markup('<p>%s</p>') % escape(message) +
                Markup('<p><a href="/odoo/ai?session_id=%s">%s</a></p>') % (
                    self.id, _("Open Chat")
                )
            )
            with suppress(Exception):
                mail_message = self.env['mail.message'].sudo().create({
                    'message_type': 'user_notification',
                    'subtype_id': self.env['ir.model.data']._xmlid_to_res_id(
                        'mail.mt_note'
                    ),
                    'model': self._name,
                    'res_id': self.id,
                    'author_id': self.env.ref('base.partner_root').id,
                    'subject': title,
                    'body': body,
                    'partner_ids': [(4, partner.id)],
                    'muk_ai_session_id': self.id,
                })
                self.env['mail.notification'].sudo().create({
                    'mail_message_id': mail_message.id,
                    'res_partner_id': partner.id,
                    'notification_type': 'inbox',
                    'is_read': False,
                })
                partner._bus_send_store(mail_message)

    # ----------------------------------------------------------
    # Helper State
    # ----------------------------------------------------------

    def _append_event(self, entry):
        stamped = (
            entry
            if 'at' in entry
            else {**entry, 'at': fields.Datetime.now().isoformat()}
        )
        event = self.env['muk_ai.session.event'].sudo()
        for _attempt in range(5):
            self.env.cr.execute(SQL(
                "SELECT COALESCE(MAX(sequence), -1) + 1 "
                "FROM muk_ai_session_event WHERE session_id = %s",
                self.id,
            ))
            sequence = self.env.cr.fetchone()[0]
            try:
                with self.env.cr.savepoint():
                    event = self.env['muk_ai.session.event'].sudo().create({
                        'session_id': self.id,
                        'sequence': sequence,
                        'kind': stamped.get('kind') or '',
                        'payload': {**stamped, 'event_id': None},
                        'at': fields.Datetime.now(),
                    })
                event.payload = {**stamped, 'event_id': event.id}
                stamped = {**stamped, 'event_id': event.id}
                break
            except psycopg2.errors.UniqueViolation:
                continue
        self._publish_event('log', stamped)
        return event

    def _extend_conversation(self, items):
        self.conversation = [*(self.conversation or []), *(items or [])]

    def _resolve_attachments(self, attachment_ids):
        requested = self.env['ir.attachment'].browse([
            int(aid) for aid in attachment_ids or []
        ])
        if (attachments := requested.exists()) != requested:
            raise UserError(_("One or more attachments could not be found."))
        attachments._ai_validate()
        if new := attachments - self.attachment_ids:
            self.sudo().write({'attachment_ids': [(4, a.id) for a in new]})
            new.sudo().write({'res_model': 'muk_ai.session', 'res_id': self.id})
        return attachments

    def _enqueue_user_turn(self, user_message, attachments, extend=True):
        if extend and (user_entry := self._build_user_entry(
            user_message, attachments
        )):
            self._extend_conversation([user_entry])
        if user_message or attachments:
            self._append_event(self._user_message_log(
                user_message, attachments
            ))
        self.write({'state': 'running', 'error_message': False})
        self._publish_event('state', {'state': 'running'})

    def _record_tool_result(
        self, outputs, call_id, name, output_result, log_result=None
    ):
        outputs.append(build_tool_call_output(call_id, output_result))
        self._append_event({
            'kind': 'tool_result',
            'name': name,
            'result': output_result if log_result is None else log_result,
            'call_id': call_id,
        })

    def _persist_synthetic_event(self, call, result, status):
        arguments = call.get('arguments') or {}
        self.env['muk_mcp.log'].sudo().create({
            'method': 'tools/call',
            'tool_name': call.get('name') or '',
            'model_name': (
                arguments.get('model') or ''
                if isinstance(arguments, dict) else ''
            ),
            'user_id': self.env.uid,
            'status': status,
            'duration_ms': 0,
            'request_data': json.dumps(arguments, default=str),
            'response_data': json.dumps(result, default=str),
            'error_message': (
                result.get('error') or result.get('reason')
                if isinstance(result, dict) else None
            ),
            'source': 'chat',
            'session_id': self.id,
        })

    def _commit_safe(self):
        if not modules.module.current_test:
            for attempt in range(1, MAX_TRIES_ON_CONCURRENCY_FAILURE + 1):
                try:
                    self.env.cr.commit()
                    return
                except PG_CONCURRENCY_EXCEPTIONS_TO_RETRY as exc:
                    self.env.cr.rollback()
                    if attempt == MAX_TRIES_ON_CONCURRENCY_FAILURE:
                        self.invalidate_recordset()
                        return
                    time.sleep(random.uniform(0.0, 0.2 * (2 ** (attempt - 1))))

    def _transition_state(self, state, error=None):
        self.write({'state': state} | ({'error_message': error} if error else {}))
        self._publish_event('state', {'state': state} | ({'error': error} if error else {}))

    def _recover_if_stuck(self, idle_seconds=WORKER_STALE_THRESHOLD):
        if (
            self.state in ('running', 'compacting')
            and (reference := self.claimed_at or self.write_date)
        ):
            idle = (fields.Datetime.now() - reference).total_seconds()
            if idle >= idle_seconds and self._try_session_xact_lock(self.id):
                had_queue = bool(self.pending_ids)
                if had_queue:
                    self.pending_ids.unlink()
                    self.invalidate_recordset(['pending_ids'])
                self.write({
                    'state': 'error',
                    'error_message': _(
                        "Previous turn timed out after %(idle)s seconds with no activity.",
                        idle=int(idle),
                    ),
                })
                self._publish_event('state', {
                    'state': 'error',
                    'error': self.error_message
                })
                if had_queue:
                    self._publish_event('queue', {'pending': []})
                return True
        return False

    @api.model
    def _try_session_xact_lock(self, session_id):
        self.env.cr.execute(SQL(
            "SELECT pg_try_advisory_xact_lock(%s, %s)",
            ADVISORY_LOCK_NAMESPACE, session_id,
        ))
        return self.env.cr.fetchone()[0]

    def _heartbeat_claim(self):
        if self:
            self.sudo().write({
                'claimed_at': fields.Datetime.now()
            })
            self._commit_safe()

    # ----------------------------------------------------------
    # Helper Rate Limit
    # ----------------------------------------------------------

    @api.model
    def _get_rate_limit(self):
        provider = self.env['muk_ai.provider']._get_default()
        return max(0, provider.rate_limit or 0) if provider else 0

    @api.model
    def _check_rate_limit(self, batch_size=1):
        if limit := self._get_rate_limit():
            count = self.sudo().search_count([
                ('user_id', '=', self.env.user.id),
                ('create_date', '>=', fields.Datetime.now() - timedelta(minutes=1)),
            ])
            if count + batch_size > limit:
                raise UserError(_(
                    "Rate limit reached (%(count)s sessions in the last minute.",
                    count=count
                ))

    # ----------------------------------------------------------
    # Helper Tool Dispatch
    # ----------------------------------------------------------

    def _tool_dispatch_context(self):
        return {'muk_mcp_session_id': self.id}

    def _dispatch_tool_call(self, name, arguments, call_id):
        if name == 'tool_load':
            return self._dispatch_tool_load(arguments, parent_call_id=call_id), True
        enforce_scope = 'read' if self.agent_id and self.agent_id.read_only else None
        arguments, resolved_refs = self._resolve_value_refs(arguments)
        try:
            tool_env = self.env(context={
                **self.env.context, **self._tool_dispatch_context()
            })
            text, _info = tool_env['muk_mcp.tool']._call(
                name, arguments, tool_env, enforce_scope=enforce_scope
            )
        except Exception as error:
            return {'error': str(error)}, False
        self._maybe_publish_ui_action(text, name, call_id)
        if previews := [r['preview_url'] for r in resolved_refs if r.get('preview_url')]:
            if isinstance(text, str):
                text += '\n\n' + '\n\n'.join(f'![image set]({u})' for u in previews)
            elif isinstance(text, dict):
                text = {**text, 'image_previews': previews}
        return text, True

    def _dispatch_tool_load(self, arguments, parent_call_id=None):
        bad_names = {'error': "Argument 'names' must be a non-empty list of tool name strings."}
        requested = arguments.get('names') if isinstance(arguments, dict) else None
        if not isinstance(requested, list):
            return bad_names
        names = [
            str(item).strip()
            for item in requested
            if isinstance(item, (str, int)) and str(item).strip()
        ]
        if not names:
            return bad_names
        catalog_by_name = {entry['name']: entry for entry in self._get_filtered_catalog()}
        loaded = {}
        unknown = []
        for name in names:
            if entry := catalog_by_name.get(name):
                loaded[name] = {
                    'description': entry.get('description') or '',
                    'inputSchema': (
                        entry.get('inputSchema') or
                        {'type': 'object', 'properties': {}}
                    ),
                }
            else:
                unknown.append(name)
        if loaded:
            self.write({'expanded_tool_names': list(dict.fromkeys(
                list(self.expanded_tool_names or []) + list(loaded)
            ))})
        response = {'loaded': loaded, 'unknown': unknown}
        if call_spec := (arguments.get('call') if isinstance(arguments, dict) else None):
            response['call'] = self._dispatch_tool_load_inline_call(
                call_spec, loaded, parent_call_id
            )
        return response

    def _dispatch_tool_load_inline_call(self, call_spec, loaded, parent_call_id):
        if not isinstance(call_spec, dict):
            return {'error': "`call` must be an object with `name` and optional `arguments`."}
        if not (target := str(call_spec.get('name') or '').strip()):
            return {'error': "`call.name` is required."}
        if target not in loaded:
            return {'error': (
                f"`call.name` {target!r} must be one of the just-loaded names; "
                "include it in `names` and try again."
            )}
        target_args = call_spec.get('arguments') or {}
        if not isinstance(target_args, dict):
            return {'error': "`call.arguments` must be an object."}
        inline_call_id = f"{parent_call_id or 'tool_load'}__{target}"
        self._record_tool_call({
            'name': target,
            'arguments': target_args,
            'call_id': inline_call_id
        })
        result, ok = self._dispatch_tool_call(
            target, target_args, inline_call_id
        )
        self._append_event({
            'kind': 'tool_result',
            'name': target,
            'result': result,
            'call_id': inline_call_id,
        })
        return {'name': target, 'output': result, 'ok': ok}

    def _maybe_publish_ui_action(self, text, name, call_id):
        try:
            action = (
                json.loads(text)
                if isinstance(text, str)
                else None
            )
        except ValueError:
            action = None
        if (
            isinstance(action, dict)
            and isinstance(t := action.get('type'), str)
            and t.startswith('ir.actions.')
        ):
            self._publish_event('ui_action', {
                'call_id': call_id,
                'name': name,
                'action': action
            })
            if name in self._get_terminating_tools():
                self._apply_ui_action(name, action)

    # ----------------------------------------------------------
    # Helper View Context
    # ----------------------------------------------------------

    def _apply_ui_action(self, tool_name, action):
        if payload := self._view_context_from_action(tool_name, action):
            self._write_view_context(payload)

    def _view_context_from_action(self, tool_name, action):
        if isinstance(action, dict) and (res_model := action.get('res_model')):
            if tool_name == 'open_record' or action.get('view_mode') == 'form':
                if res_id := action.get('res_id'):
                    record = self.env[res_model].sudo().browse(int(res_id))
                    return {
                        'kind': 'record',
                        'model': res_model,
                        'id': int(res_id),
                        'display_name': record.exists().display_name or str(res_id),
                    }
            else:
                payload = {
                    'kind': 'list',
                    'model': res_model,
                    'view_type': (action.get('view_mode') or '').split(',')[0] or 'list',
                }
                if isinstance(domain := action.get('domain'), list) and domain:
                    payload['domain'] = domain
                if (action_id := action.get('id')) and tool_name == 'open_action':
                    payload.update(kind='action', action_id=action_id)
                return payload
        return None

    def _enrich_view_context(self, payload):
        return payload

    def _write_view_context(self, payload):
        if payload:
            payload = self._enrich_view_context(payload)
        self.write({'view_context': payload or False})
        self._publish_event('view_context', {'view_context': payload or None})

    # ----------------------------------------------------------
    # Helper Streaming
    # ----------------------------------------------------------

    def _check_cancelled(self, buffer_state):
        last = buffer_state.get('last_state_check', 0)
        if (now := time.monotonic()) - last >= 0.3:
            buffer_state['last_state_check'] = now
            self.invalidate_recordset(['state'])
            if self.state == 'stopped':
                if buffer_state.get('full_text'):
                    self._persist_partial(buffer_state)
                    buffer_state['full_text'] = ''
                    self._commit_safe()
                raise StreamCancelled()
            last_beat = buffer_state.get('last_heartbeat', 0)
            if now - last_beat >= WORKER_HEARTBEAT_INTERVAL:
                buffer_state['last_heartbeat'] = now
                self.claimed_at = fields.Datetime.now()
                self._commit_safe()

    def _on_stream_delta(self, kind, payload, buffer_state):
        self._check_cancelled(buffer_state)
        if kind == 'text':
            if delta := (payload or {}).get('delta') or '':
                buffer_state['full_text'] = buffer_state.get('full_text', '') + delta
                self._coalesce_and_emit(
                    buffer_state,
                    'text',
                    'last_text_flush',
                    delta,
                    'text_delta'
                )
        elif kind == 'reasoning':
            if delta := (payload or {}).get('delta') or '':
                self._coalesce_and_emit(
                    buffer_state,
                    'reasoning',
                    'last_reasoning_flush',
                    delta,
                    'reasoning_delta'
                )
        elif kind == 'tool_start':
            self._flush_text_buffer(buffer_state)
            self._publish_event('tool_call_start', {
                'call_id': payload.get('call_id'),
                'name': payload.get('name'),
            })
            self._commit_safe()
        elif kind == 'tool_args':
            call_id = payload.get('call_id')
            delta = payload.get('delta') or ''
            if call_id and delta:
                key = f'tool_args_{call_id}'
                self._coalesce_and_emit(
                    buffer_state,
                    key,
                    key + '_last',
                    delta,
                    'tool_call_args_delta',
                    extra={'call_id': call_id},
                )

    def _coalesce_and_emit(
        self,
        buffer_state,
        content_key,
        last_key,
        delta,
        event_type,
        extra=None
    ):
        now = time.monotonic()
        buffer_state.setdefault(content_key, '')
        buffer_state.setdefault(last_key, now)
        buffer_state[content_key] += delta
        if (
            len(buffer_state[content_key]) >= 80 or
            (now - buffer_state[last_key]) >= 0.1
        ):
            flushed = buffer_state[content_key]
            buffer_state[content_key] = ''
            buffer_state[last_key] = now
            self._publish_event(event_type, {
                'delta': flushed, **(extra or {})
            })
            self._commit_safe()

    def _flush_text_buffer(self, buffer_state):
        if flushed := buffer_state.get('text'):
            buffer_state['text'] = ''
            self._publish_event('text_delta', {
                'delta': flushed
            })
            self._commit_safe()

    def _persist_partial(self, buffer_state):
        if text := buffer_state.get('full_text'):
            self.write({
                'last_text': text,
                'conversation': [*(self.conversation or []), {
                    'type': 'message',
                    'role': 'assistant',
                    'content': [{'type': 'output_text', 'text': text}],
                }],
            })
            self._append_event({
                'kind': 'text',
                'content': text
            })
            self.flush_recordset()

    def _flush_stream_buffer(self, buffer_state):
        self._flush_text_buffer(buffer_state)
        if flushed := buffer_state.get('reasoning'):
            buffer_state['reasoning'] = ''
            self._publish_event('reasoning_delta', {
                'delta': flushed
            })
        for key in list(buffer_state.keys()):
            if key.startswith('tool_args_') and not key.endswith('_last'):
                if flushed := buffer_state.get(key):
                    buffer_state[key] = ''
                    self._publish_event('tool_call_args_delta', {
                        'call_id': key[len('tool_args_'):],
                        'delta': flushed,
                    })
        self._commit_safe()

    def _stream_provider_round(self, provider, tool_schema, model, agent):
        buffer_state = {'text': '', 'last_text_flush': time.monotonic()}
        try:
            payload = provider._request_responses(
                inputs=self._build_request_inputs(),
                tools_schema=tool_schema,
                model=model,
                on_delta=lambda kind, data: self._on_stream_delta(kind, data, buffer_state),
                enable_web_search=bool(agent and agent.enable_web_search),
                enable_image_generation=bool(agent and agent.enable_image_generation),
                enable_code_interpreter=bool(agent and agent.enable_code_interpreter),
            )
            self._flush_stream_buffer(buffer_state)
            return payload
        except StreamCancelled:
            self._flush_stream_buffer(buffer_state)
            raise

    # ----------------------------------------------------------
    # Auto-name
    # ----------------------------------------------------------

    def _autoname_from_text(self, raw):
        text = re.sub(r'\s+', ' ', (raw or '')).strip()
        text = re.split(r'[.!?\n;:]', text, maxsplit=1)[0].strip()
        text = text.strip('"\'`“”‘’,. -').strip()
        if not text:
            return ''
        words = text.split(' ')
        if len(words) > 6:
            text = ' '.join(words[:6])
        return text[:60].rstrip(' ,;:-')

    # ----------------------------------------------------------
    # Helper Agent Loop
    # ----------------------------------------------------------

    def _accrue_cost_deltas(self, usage):
        if record := self._effective_model_record():
            delta = record._compute_usage_cost(usage or {})
            return {
                'total_input_cost': (self.total_input_cost or 0.0) + delta['input_cost'],
                'total_output_cost': (self.total_output_cost or 0.0) + delta['output_cost'],
                'total_cost': (self.total_cost or 0.0) + delta['total_cost'],
            }
        return {}

    def _persist_inline_images(self, text, cache=None):
        if text and 'data:image/' in text:
            if cache is None:
                cache = {}

            def _replace(match):
                alt = match.group(1) or 'generated.png'
                mimetype = match.group(2)
                b64 = re.sub(r'\s+', '', match.group(3))
                if cached := cache.get(b64):
                    attachment_id = cached
                else:
                    try:
                        attachment = self.env['ir.attachment'].sudo()._ai_create_from_upload(
                            alt or 'generated.png',
                            mimetype,
                            b64,
                            res_id=self.id,
                        )
                    except Exception:
                        return match.group(0)
                    attachment_id = attachment.id
                    cache[b64] = attachment_id
                return (
                    f'![{alt}](/web/image/{attachment_id}) '
                    f'_(attachment {attachment_id} — to set on a record use '
                    f'`image_1920="@attachment:{attachment_id}"`)_'
                )

            return INLINE_IMAGE_RE.sub(_replace, text)
        return text

    def _persist_inline_images_in_carry(self, items, cache):
        out = []
        for item in items or []:
            if isinstance(item, dict) and isinstance(content := item.get('content'), list):
                out.append({**item, 'content': [
                    {**c, 'text': self._persist_inline_images(c['text'], cache=cache)}
                    if isinstance(c, dict) and isinstance(c.get('text'), str) and 'data:image/' in c['text']
                    else c
                    for c in content
                ]})
            else:
                out.append(item)
        return out

    def _resolve_value_refs(self, arguments):
        refs = []
        if isinstance(arguments, dict):

            def _resolve(value):
                if isinstance(value, str):
                    if m := ATTACHMENT_REF_RE.match(value):
                        attachment = self.env['ir.attachment'].sudo().browse(
                            int(m.group(1))
                        )
                        if (
                            attachment.exists() and
                            attachment.datas and
                            attachment.file_size <= ATTACHMENT_REF_MAX_BYTES and
                            (not attachment.mimetype or attachment.mimetype in ALLOWED_MIMETYPES)
                        ):
                            refs.append({
                                'kind': 'attachment',
                                'preview_url': f'/web/image/{attachment.id}'
                            })
                            return attachment.datas.decode()
                        return value
                    if m := URL_REF_RE.match(value):
                        url = m.group(1)
                        try:
                            content = fetch_url(url)
                        except (UserError, urllib3.exceptions.HTTPError):
                            return value
                        refs.append({
                            'kind': 'url',
                            'preview_url': url
                        })
                        return base64.b64encode(content).decode()
                    return value
                if isinstance(value, dict):
                    return {k: _resolve(v) for k, v in value.items()}
                if isinstance(value, list):
                    return [_resolve(v) for v in value]
                return value

            return _resolve(arguments), refs
        return arguments, refs

    def _accrue_usage(self, usage):
        usage = usage or {}
        round_input_tokens = usage.get('input_tokens')
        self.write({
            'iteration_count': self.iteration_count + 1,
            'total_input_tokens': self.total_input_tokens + (round_input_tokens or 0),
            'total_output_tokens': self.total_output_tokens + usage.get('output_tokens', 0),
            'last_input_tokens': (
                self.last_input_tokens
                if round_input_tokens is None
                else round_input_tokens
            ),
            **self._accrue_cost_deltas(usage),
        })

    def _accrue_round_payload(self, payload):
        usage = payload.get('usage') or {}
        self._accrue_usage(usage)
        image_cache = {}
        if (text := payload.get('text')) and 'data:image/' in text:
            text = self._persist_inline_images(text, cache=image_cache)
            payload['text'] = text
        if text:
            self.last_text = text
            self._append_event({'kind': 'text', 'content': text})
        self._extend_conversation(
            self._persist_inline_images_in_carry(
                payload.get('carry_inputs') or [], image_cache
            ),
        )

    def _finalize_round(self, payload):
        if payload.get('text'):
            self._transition_state('done')
        else:
            self._transition_state(
                'error', error=_("AI returned no output.")
            )

    def _skip_reason(self, has_ask_user, has_terminating):
        if has_ask_user:
            return 'skipped: ask_user pending, call again after user answer'
        if has_terminating:
            return 'skipped: terminating tool already ran; emit a short summary and stop'
        return None

    def _record_tool_call(self, call):
        event = {
            'kind': 'tool_call',
            'name': call['name'],
            'arguments': call['arguments'],
            'call_id': call['call_id'],
        }
        event.update(self._tool_call_event_extra(
            call
        ))
        self._append_event(event)

    def _tool_call_event_extra(self, call):
        return {}

    def _skip_tool_call(self, outputs, call, reason, log_result=None):
        result = {'error': reason}
        self._persist_synthetic_event(call, result, 'denied')
        self._record_tool_result(
            outputs,
            call['call_id'],
            call['name'],
            result,
            log_result=log_result
        )

    def _register_ask_user(self, call):
        args = call['arguments'] or {}
        ask = {
            'call_id': call['call_id'],
            'text': args.get('question'),
            'options': args.get('options'),
            'resolution': args.get('resolution') or 'text',
            'preview': args.get('preview') or None,
        }
        self.pending_ask = {'kind': 'question', **ask}
        self._append_event({'kind': 'ask_user', **ask})

    def _execute_tool_call(self, call, tool_calls, outputs, index, has_terminating):
        gate = self._check_approval_gate(call['name'], call['arguments'])
        if gate['action'] == 'pause':
            self._enter_waiting_approval(
                call,
                tool_calls,
                outputs,
                index,
                has_terminating,
                gate
            )
            return None
        self._record_tool_call(call)
        if gate['action'] == 'auto_approved':
            self._record_approval_audit(
                decision='auto_approved',
                call=call,
                risk=gate['risk']
            )
        self._heartbeat_claim()
        result, ok = self._dispatch_tool_call(
            call['name'],
            call['arguments'],
            call['call_id']
        )
        self._heartbeat_claim()
        self._record_tool_result(
            outputs,
            call['call_id'],
            call['name'],
            result
        )
        return ok and call['name'] in self._get_terminating_tools()

    def _process_tool_round(self, tool_calls, outputs, start_index, has_terminating=False):
        has_ask_user = any(c.get('name') == 'ask_user' for c in tool_calls)
        wait_for_user, paused = False, False
        for index in range(start_index, len(tool_calls)):
            call = tool_calls[index]
            if index >= MAX_TOOL_CALLS_PER_ROUND:
                self._record_tool_call(call)
                self._skip_tool_call(outputs, call, 'tool_call_limit_exceeded',
                    log_result={'error': 'tool_call_limit_exceeded'})
                continue
            if call.get('_parse_error'):
                self._record_tool_call(call)
                self._skip_tool_call(outputs, call, call['_parse_error'])
                continue
            if call['name'] == 'ask_user':
                self._register_ask_user(call)
                wait_for_user = True
                continue
            if skip := self._skip_reason(has_ask_user, has_terminating):
                self._record_tool_call(call)
                self._skip_tool_call(
                    outputs, call, skip, log_result={'error': 'skipped'}
                )
                continue
            outcome = self._execute_tool_call(
                call, tool_calls, outputs, index, has_terminating
            )
            if outcome is None:
                paused = True
                break
            has_terminating = has_terminating or outcome
        if not paused:
            self._extend_conversation(outputs)
            if wait_for_user:
                self.write({'state': 'waiting'})
                self._publish_event('state', {
                    'state': 'waiting',
                    'ask': self.pending_ask
                })
        return None if paused or wait_for_user else has_terminating

    def _run_to_completion(self, has_terminating=False):
        deadline = time.monotonic() + MAX_WALLCLOCK_SECONDS
        while True:
            self._maybe_auto_compact()
            if self.state != 'running':
                return
            self._run_iterations(
                has_terminating=has_terminating,
                deadline=deadline
            )
            if self.state != 'done':
                return
            if not self._drain_pending_message():
                return
            if time.monotonic() > deadline:
                self._transition_state('error', error=_(
                    "Wallclock cap reached (%(s)s s). Send a new message to continue.",
                    s=MAX_WALLCLOCK_SECONDS,
                ))
                return
            self._transition_state('running')
            has_terminating = False

    def _run_iterations(self, has_terminating=False, deadline=None):
        deadline = deadline or time.monotonic() + MAX_WALLCLOCK_SECONDS
        provider, model = self._effective_provider(), self._effective_model()
        for _iteration in range(MAX_ITERATIONS):
            if self.state != 'running':
                return
            if time.monotonic() > deadline:
                self._transition_state('error', error=_(
                    "Wallclock cap reached (%(s)s s). Send a new message to continue.",
                    s=MAX_WALLCLOCK_SECONDS,
                ))
                return
            self.invalidate_recordset(['pending_ids', 'expanded_tool_names'])
            if self.pending_ids and self._drain_pending_message():
                has_terminating = False
            tool_schema = self._get_tool_schema()
            schema, round_agent = (
                (None, None)
                if has_terminating
                else (tool_schema, self.agent_id)
            )
            try:
                payload = self._stream_provider_round(
                    provider, schema, model, round_agent
                )
            except StreamCancelled:
                self.invalidate_recordset(['state'])
                if self.state == 'stopped':
                    self._publish_event('state', {'state': 'stopped'})
                return
            except UserError as error:
                self._transition_state('error', error=str(error))
                return
            self._accrue_round_payload(payload)
            if not (tool_calls := payload.get('tool_calls') or []):
                self._finalize_round(payload)
                return
            result = self._process_tool_round(
                tool_calls, [], 0, has_terminating=has_terminating
            )
            if result is None:
                return
            has_terminating = has_terminating or result
        if self.state == 'running':
            self._transition_state(
                'error', error=_("Maximum iterations reached.")
            )

    # ----------------------------------------------------------
    # Queue
    # ----------------------------------------------------------

    def _serialize_pending(self):
        return [p._to_payload() for p in self.pending_ids]

    def enqueue_message(self, user_message, attachment_ids=None):
        self.env['muk_ai.session.pending'].create({
            'session_id': self.id,
            'content': user_message or '',
            'attachment_ids': list(attachment_ids or []),
        })
        self.invalidate_recordset(['pending_ids'])
        self._publish_event('queue', {'pending': self._serialize_pending()})
        return self.get_snapshot()

    def cancel_queued(self, index):
        pending = self.pending_ids
        if 0 <= index < len(pending):
            pending[index].unlink()
            self.invalidate_recordset(['pending_ids'])
            self._publish_event('queue', {'pending': self._serialize_pending()})
        return self.get_snapshot()

    def _drain_pending_message(self):
        if pending := self.pending_ids:
            contents = [p.content or '' for p in pending]
            attachment_ids = [aid for p in pending for aid in (p.attachment_ids or [])]
            combined = '\n\n'.join(c for c in contents if c.strip())
            pending.unlink()
            self.invalidate_recordset(['pending_ids'])
            self._publish_event('queue', {'pending': []})
            attachments = self._resolve_attachments(attachment_ids)
            self._enqueue_user_turn(combined, attachments)
            return True
        return False

    # ----------------------------------------------------------
    # Helper Approval
    # ----------------------------------------------------------

    def _require_pending_approval(self):
        pending = dict(self.pending_ask or {})
        if self.state != 'waiting' or pending.get('kind') != 'approval':
            raise UserError(_("Session is not waiting for approval."))
        return pending

    def _check_approval_gate(self, name, arguments):
        if self._effective_approval_mode() == 'off':
            return {'action': 'dispatch'}
        risk = self.env['muk_ai.approval']._assess_risk(name, arguments)
        if not risk:
            return {'action': 'dispatch'}
        if risk['signature'] in (self.approved_signatures or []):
            return {'action': 'auto_approved', 'risk': risk}
        return {'action': 'pause', 'risk': risk}

    def _enter_waiting_approval(
        self,
        call,
        tool_calls,
        outputs,
        index,
        has_terminating,
        gate,
    ):
        risk = gate['risk']
        preview = self.env['muk_ai.approval']._build_preview(
            call['name'], call['arguments']
        ) or {}
        pending = {
            'kind': 'approval',
            'call_id': call['call_id'],
            'text': risk.get('reason') or '',
            'resolution': 'yesno',
            'preview': preview,
            'name': call['name'],
            'arguments': call['arguments'],
            'risk': risk,
            'tool_calls': tool_calls,
            'outputs': outputs,
            'resume_index': index,
            'has_terminating': has_terminating,
        }
        self._append_event({
            'kind': 'ask_user',
            'call_id': call['call_id'],
            'text': risk.get('reason') or '',
            'resolution': 'yesno',
            'preview': preview,
        })
        self.write({'state': 'waiting', 'pending_ask': pending})
        self._publish_event('state', {'state': 'waiting', 'ask': pending})

    def _record_approval_audit(
        self,
        decision,
        call,
        risk,
        args_executed=None,
        reject_reason=None,
    ):
        self.env['muk_ai.approval'].sudo().create({
            'session_id': self.id,
            'agent_id': self.agent_id.id if self.agent_id else False,
            'user_id': self.env.user.id,
            'decision': decision,
            'tool_name': call.get('name') or '',
            'res_model': risk.get('model') or '',
            'res_ids': risk.get('ids') or [],
            'method': risk.get('method') or '',
            'reason': risk.get('reason') or '',
            'signature': risk.get('signature') or '',
            'args_proposed': call.get('arguments') or {},
            'args_executed': (
                args_executed
                if args_executed is not None
                else (call.get('arguments') or {})
            ),
            'reject_reason': reject_reason or False,
        })

    def _resume_tool_round(self, paused, approved, reject_reason=None):
        call = {
            'call_id': paused['call_id'],
            'name': paused['name'],
            'arguments': paused['arguments'],
        }
        outputs = list(paused.get('outputs') or [])
        tool_calls = list(paused.get('tool_calls') or [])
        has_terminating = bool(paused.get('has_terminating'))
        self._record_tool_call(call)
        if approved:
            result, ok = self._dispatch_tool_call(
                call['name'], call['arguments'], call['call_id']
            )
            if ok and call['name'] in self._get_terminating_tools():
                has_terminating = True
        else:
            result = {
                'error': 'rejected_by_user',
                'reason': reject_reason or '',
            }
            self._persist_synthetic_event(call, result, 'denied')
        self._record_tool_result(
            outputs, call['call_id'], call['name'], result
        )
        self.pending_ask = False
        self._transition_state('running')
        self._process_tool_round(
            tool_calls,
            outputs,
            paused.get('resume_index', 0) + 1,
            has_terminating=has_terminating,
        )

    # ----------------------------------------------------------
    # Helper Compact
    # ----------------------------------------------------------

    def _estimate_entry_tokens(self, entry):
        if not isinstance(entry, dict):
            return 0
        total = 0
        content = entry.get('content')
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    text = block.get('text') or block.get('arguments') or ''
                    if isinstance(text, str):
                        total += len(text) // 4
        elif isinstance(content, str):
            total += len(content) // 4
        for key in ('arguments', 'output', 'text'):
            value = entry.get(key)
            if isinstance(value, str):
                total += len(value) // 4
        return total

    def _split_conversation_for_compact(self):
        keep_budget = max(2000, min(20000, self._resolve_context_window() // 5))
        tail, used = [], 0
        for entry in reversed(self.conversation or []):
            est = self._estimate_entry_tokens(entry)
            if used + est > keep_budget and tail:
                break
            tail.insert(0, entry)
            used += est
        prefix = (
            (self.conversation or [])[:-len(tail)]
            if tail else list(self.conversation or [])
        )
        prefix = [
            entry for entry in prefix
            if not (isinstance(entry, dict) and entry.get('role') == 'system')
        ]
        if not prefix:
            non_system = [
                entry for entry in (self.conversation or [])
                if not (isinstance(entry, dict) and entry.get('role') == 'system')
            ]
            if len(non_system) >= 2:
                prefix, tail = non_system[:-1], non_system[-1:]
            elif non_system:
                prefix, tail = non_system, []
        return prefix, tail

    def _find_prior_compact_summary(self):
        if not self.id:
            return None
        prior = self.env['muk_ai.session.event'].sudo().search(
            [
                ('session_id', '=', self.id),
                ('kind', 'in', ('compact_progress', 'command')),
            ],
            order='sequence desc', limit=5,
        )
        for event in prior:
            payload = event.payload or {}
            if event.kind == 'compact_progress' and payload.get('state') == 'done':
                return payload.get('summary') or None
            if event.kind == 'command' and payload.get('name') == '/compact':
                return payload.get('summary') or None
        return None

    def _pre_compact_hook(self):
        return True

    def _build_compact_inputs(self, prefix):
        budget = max(500, min(4000, self._resolve_context_window() // 200))
        prompt_parts = [COMPACT_SUMMARY_TEMPLATE, f'\nOutput ≤{budget} tokens.\n']
        if prior_summary := self._find_prior_compact_summary():
            prompt_parts.insert(0, (
                f'<previous-summary>\n{prior_summary}\n</previous-summary>\n\n'
                'Update the structure above: preserve still-true points, '
                'drop stale ones, merge new info.\n\n'
            ))
        prompt_text = ''.join(prompt_parts)
        return [
            {
                'role': 'system',
                'content': [{'type': 'input_text', 'text': COMPACT_SUMMARY_SYSTEM}],
            },
            *prefix,
            {
                'role': 'user',
                'content': [{'type': 'input_text', 'text': prompt_text}],
            },
        ]

    def _maybe_auto_compact(self):
        if self.state == 'compacting':
            return False
        window = self._resolve_context_window()
        if not window or not self.last_input_tokens:
            return False
        if (self.last_input_tokens / window) < COMPACT_AUTO_RATIO:
            return False
        if not (self.conversation or []):
            return False
        resume_state = self.state if self.state == 'running' else None
        self._begin_compact_progress(auto=True)
        self.write({'state': 'compacting'})
        self._publish_event('state', {'state': 'compacting'})
        self._do_compact()
        if resume_state and self.state == 'done':
            self.write({'state': resume_state})
            self._publish_event('state', {'state': resume_state})
        return True

    def _begin_compact_progress(self, auto=False):
        event = self._append_event({
            'kind': 'compact_progress',
            'name': '/compact',
            'auto': bool(auto),
            'state': 'streaming',
            'message_count': sum(
                1 for item in (self.conversation or [])
                if isinstance(item, dict) and item.get('role') in ('user', 'assistant')
            ),
            'tokens_estimate': self.last_input_tokens or 0,
            'started_at': fields.Datetime.now().isoformat(),
            'streamed_text': '',
        })
        return event

    def _find_active_compact_event(self):
        return self.env['muk_ai.session.event'].sudo().search([
            ('session_id', '=', self.id),
            ('kind', '=', 'compact_progress'),
        ], order='sequence desc', limit=1)

    def _patch_compact_progress(self, event, patch):
        if not event:
            return
        payload = dict(event.payload or {})
        payload.update(patch)
        event.payload = payload
        self._publish_event('compact_update', {
            'event_id': event.id,
            'patch': patch,
        })

    def _tail_drop_fallback(self, progress_event, prefix, tail, error):
        dropped = sum(
            1 for item in prefix
            if isinstance(item, dict) and item.get('role') in ('user', 'assistant')
        )
        original_messages = sum(
            1 for item in (self.conversation or [])
            if isinstance(item, dict) and item.get('role') in ('user', 'assistant')
        )
        original_tokens = self.last_input_tokens
        new_conversation = [*self._build_initial_inputs(), *tail]
        self.write({
            'conversation': new_conversation,
            'pending_ask': False,
            'error_message': False,
            'last_input_tokens': 0,
            'state': 'done',
            'cleared_at': fields.Datetime.now(),
        })
        notice = _(
            "Compaction failed (%(error)s) — dropped %(dropped)s oldest "
            "message(s) without summary as a fallback.",
            error=error or 'unknown error',
            dropped=dropped,
        )
        self._patch_compact_progress(progress_event, {
            'state': 'done',
            'summary': notice,
            'streamed_text': notice,
            'original_messages': original_messages,
            'original_tokens': original_tokens,
            'fallback': 'tail_drop',
        })
        self._publish_event('state', {'state': 'done'})
        if self.pending_ids:
            self._drain_pending_message()
            self._run_to_completion()

    def _do_compact(self):
        if not self._pre_compact_hook():
            self.write({'state': 'done'})
            self._publish_event('state', {'state': 'done'})
            return
        progress_event = self._find_active_compact_event()
        if not progress_event or (progress_event.payload or {}).get('state') != 'streaming':
            progress_event = self._begin_compact_progress(auto=False)
        prefix, tail = self._split_conversation_for_compact()
        if not prefix:
            self._patch_compact_progress(progress_event, {
                'state': 'cancelled',
                'message': _("Nothing to compact — conversation too short."),
            })
            self.write({'state': 'done'})
            self._publish_event('state', {'state': 'done'})
            return
        inputs = self._build_compact_inputs(prefix)
        stream_state = {'text': '', 'last_flush': time.monotonic()}

        def on_delta(kind, data):
            if kind != 'text':
                return
            delta = (data or {}).get('delta') or ''
            if not delta:
                return
            stream_state['text'] += delta
            self._publish_event('compact_delta', {
                'event_id': progress_event.id,
                'delta': delta,
            })
            now = time.monotonic()
            if now - stream_state['last_flush'] >= 0.5:
                stream_state['last_flush'] = now
                payload = dict(progress_event.payload or {})
                payload['streamed_text'] = stream_state['text']
                progress_event.payload = payload
                self._commit_safe()
        try:
            payload = self._effective_provider()._request_responses(
                inputs=inputs,
                tools_schema=None,
                on_delta=on_delta,
                model=self._effective_model(),
            )
        except Exception as error:
            self._tail_drop_fallback(progress_event, prefix, tail, str(error))
            return
        if (progress_event.payload or {}).get('state') == 'cancelled':
            self.write({'state': 'done'})
            self._publish_event('state', {'state': 'done'})
            return
        self._accrue_usage(payload.get('usage') or {})
        summary = (payload.get('text') or stream_state['text'] or '').strip()
        if not summary:
            self._patch_compact_progress(progress_event, {
                'state': 'cancelled',
                'message': _("Compaction skipped: provider returned no summary."),
            })
            self.write({'state': 'done'})
            self._publish_event('state', {'state': 'done'})
            return
        original_messages = sum(
            1 for item in (self.conversation or [])
            if isinstance(item, dict) and item.get('role') in ('user', 'assistant')
        )
        original_tokens = self.last_input_tokens
        new_conversation = [
            *self._build_initial_inputs(),
            {
                'type': 'message',
                'role': 'assistant',
                'content': [{
                    'type': 'output_text',
                    'text': f'{COMPACT_SUMMARY_REINJECTION}\n\n{summary}',
                }],
            },
            *tail,
        ]
        self.write({
            'conversation': new_conversation,
            'pending_ask': False,
            'error_message': False,
            'last_input_tokens': 0,
            'state': 'done',
            'cleared_at': fields.Datetime.now(),
        })
        self._patch_compact_progress(progress_event, {
            'state': 'done',
            'summary': summary,
            'streamed_text': summary,
            'original_messages': original_messages,
            'original_tokens': original_tokens,
        })
        self._publish_event('state', {'state': 'done'})
        if self.pending_ids:
            self._drain_pending_message()
            self._run_to_completion()

    # ----------------------------------------------------------
    # Helper History
    # ----------------------------------------------------------

    def _resolve_event(self, event_id):
        self.ensure_one()
        event = self.env['muk_ai.session.event'].sudo().search([
            ('session_id', '=', self.id),
            ('id', '=', int(event_id)),
        ], limit=1)
        if not event:
            raise UserError(_("Event not found in this session."))
        return event

    def _conversation_cut_index(self, event):
        earlier_user_msgs = self.env['muk_ai.session.event'].sudo().search_count([
            ('session_id', '=', self.id),
            ('sequence', '<', event.sequence),
            ('kind', '=', 'user_message'),
        ])
        conv = list(self.conversation or [])
        user_seen = 0
        if event.kind == 'user_message':
            for i, item in enumerate(conv):
                if isinstance(item, dict) and item.get('role') == 'user':
                    if user_seen == earlier_user_msgs:
                        return i
                    user_seen += 1
            return len(conv)
        for i, item in enumerate(conv):
            if isinstance(item, dict) and item.get('role') == 'user':
                user_seen += 1
                if user_seen == earlier_user_msgs:
                    return i + 1
        return len(conv)

    def _conversation_cut_index_for_fork(self, event):
        earlier_user_msgs = self.env['muk_ai.session.event'].sudo().search_count([
            ('session_id', '=', self.id),
            ('sequence', '<', event.sequence),
            ('kind', '=', 'user_message'),
        ])
        conv = list(self.conversation or [])
        user_seen = 0
        if event.kind == 'user_message':
            for i, item in enumerate(conv):
                if isinstance(item, dict) and item.get('role') == 'user':
                    if user_seen == earlier_user_msgs:
                        return i + 1
                    user_seen += 1
            return len(conv)
        for i, item in enumerate(conv):
            if isinstance(item, dict) and item.get('role') == 'user':
                user_seen += 1
                if user_seen > earlier_user_msgs:
                    return i
        return len(conv)

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    def fetch_events(self, limit=100, before_sequence=None):
        if self.id:
            domain = [('session_id', '=', self.id)]
            if before_sequence is not None:
                domain.append(('sequence', '<', before_sequence))
            rows = self.env['muk_ai.session.event'].sudo().search(
                domain,
                order='sequence desc, id desc',
                limit=limit + 1,
            )
            has_more = len(rows) > limit
            rows = rows[:limit]
            events = []
            for event in reversed(rows):
                payload = dict(event.payload or {})
                payload.setdefault('kind', event.kind)
                payload['event_id'] = event.id
                if not payload.get('at') and event.at:
                    payload['at'] = event.at.isoformat()
                events.append(payload)
            return {
                'events': events,
                'has_more_older': has_more,
                'oldest_sequence': rows[-1].sequence if rows else None,
            }
        return {
            'events': [],
            'has_more_older': False,
            'oldest_sequence': None,
        }

    def get_snapshot(self):
        events_window = self.fetch_events(limit=100)
        return {
            'id': self.id,
            'events': events_window['events'],
            'has_more_older': events_window['has_more_older'],
            'oldest_sequence': events_window['oldest_sequence'],
            'conversation': self.conversation or [],
            'error_message': self.error_message,
            'last_text': self.last_text,
            'attachments': [a._ai_describe() for a in self.attachment_ids],
            'total_input_cost': self.total_input_cost,
            'total_output_cost': self.total_output_cost,
            'pending_user_messages': self._serialize_pending(),
            **self._state_metrics(),
        }

    def dismiss_notifications(self):
        if partner := self.env.user.partner_id:
            messages = self.env['mail.message'].sudo().search([
                ('muk_ai_session_id', 'in', self.ids),
                ('notification_ids.res_partner_id', '=', partner.id),
                ('notification_ids.is_read', '=', False),
            ])
            if messages:
                messages.with_user(self.env.user).set_message_done()
            return True
        return False

    def start(self, user_message=None, attachment_ids=None):
        self._recover_if_stuck()
        if self.state not in ('new', 'error', 'stopped'):
            raise UserError(_("Session is not in a startable state."))
        attachments = self._resolve_attachments(attachment_ids)
        if not self.conversation:
            if title := self._autoname_from_text(user_message):
                self.write({'name': title})
                with suppress(Exception):
                    self._publish_event('rename', {'name': title})
            self.conversation = self._build_initial_inputs(user_message, attachments)
            self._enqueue_user_turn(user_message, attachments, extend=False)
        else:
            self._enqueue_user_turn(user_message, attachments)
        self._trigger_worker()
        return self.get_snapshot()

    def answer(self, answer, attachment_ids=None):
        self._recover_if_stuck()
        pending = self.pending_ask or {}
        if self.state != 'waiting' or pending.get('kind') != 'question':
            raise UserError(_("Session is not waiting for user input."))
        question = pending.get('text') or ''
        attachments = self._resolve_attachments(attachment_ids)
        if call_id := pending.get('call_id'):
            self._extend_conversation([build_tool_call_output(call_id, {
                'status': 'answered',
                'question': question,
                'answer': answer,
            })])
            if attachments:
                self._extend_conversation([self._build_user_entry(None, attachments)])
        else:
            followup_text = f'Answer to "{question}": {answer}' if question else answer
            if user_entry := self._build_user_entry(followup_text, attachments):
                self._extend_conversation([user_entry])
        self._append_event({
            'kind': 'answer',
            'question': question,
            'answer': answer,
            'attachments': [a._ai_describe() for a in attachments],
        })
        self.write({'state': 'running', 'pending_ask': False})
        self._publish_event('state', {'state': 'running'})
        self._trigger_worker()
        return self.get_snapshot()

    def send_message(self, user_message, attachment_ids=None):
        self._recover_if_stuck()
        if self.state in ('running', 'compacting'):
            return self.enqueue_message(user_message, attachment_ids=attachment_ids)
        if self.state == 'waiting':
            kind = (self.pending_ask or {}).get('kind')
            if kind == 'approval':
                return self.enqueue_message(user_message, attachment_ids=attachment_ids)
            if kind == 'question':
                return self.answer(user_message, attachment_ids=attachment_ids)
        if not self.conversation:
            return self.start(user_message, attachment_ids=attachment_ids)
        attachments = self._resolve_attachments(attachment_ids)
        self._enqueue_user_turn(user_message, attachments)
        self._trigger_worker()
        return self.get_snapshot()

    def regenerate_last_turn(self):
        if self.state in ('running', 'waiting'):
            raise UserError(_(
                "Cannot regenerate while the session is running or waiting."
            ))
        conv = list(self.conversation or [])
        last_user = next(
            (
                idx for idx in range(len(conv) - 1, -1, -1)
                if isinstance(conv[idx], dict)
                and conv[idx].get('role') == 'user'
            ),
            None,
        )
        if last_user is None:
            raise UserError(_("No user turn to regenerate from."))
        self.conversation = conv[:last_user + 1]
        events = self.env['muk_ai.session.event'].sudo().search(
            [('session_id', '=', self.id)],
            order='sequence, id',
        )
        last_user_event = next(
            (event for event in reversed(events) if event.kind == 'user_message'),
            None,
        )
        stale = events.filtered(lambda event: (
            event.sequence > last_user_event.sequence
            or (
                event.sequence == last_user_event.sequence
                and event.id > last_user_event.id
            )
        )) if last_user_event else events
        if stale:
            stale.sudo().unlink()
        self.write({
            'pending_ask': False,
            'error_message': False,
            'state': 'running',
        })
        self._publish_event('state', {'state': 'running'})
        self._trigger_worker()
        return self.get_snapshot()

    def clear(self):
        if self.state in ('running', 'compacting'):
            raise UserError(_(
                "Cannot clear the conversation while the session is running."
            ))
        if self.pending_ids:
            self.pending_ids.unlink()
            self.invalidate_recordset(['pending_ids'])
        self.write({
            'conversation': [],
            'pending_ask': False,
            'approved_signatures': [],
            'last_text': False,
            'error_message': False,
            'iteration_count': 0,
            'last_input_tokens': 0,
            'state': 'new',
            'cleared_at': fields.Datetime.now(),
        })
        self._append_event({
            'kind': 'command',
            'name': '/clear',
            'message': _("Context cleared."),
        })
        self._publish_event('state', {'state': 'new'})
        self._publish_event('queue', {'pending': []})
        return self.get_snapshot()

    def compact(self):
        if self.state in ('running', 'compacting'):
            raise UserError(_(
                "Cannot compact while the session is running. Stop first."
            ))
        if self.state == 'waiting':
            raise UserError(_(
                "Cannot compact while the session is waiting for user input."
            ))
        if not self.conversation:
            raise UserError(_(
                "Nothing to compact yet — the conversation is empty."
            ))
        self._begin_compact_progress(auto=False)
        self.write({'state': 'compacting', 'error_message': False})
        self._publish_event('state', {'state': 'compacting'})
        self._trigger_worker()
        return self.get_snapshot()

    def stop_compact(self):
        if self.state != 'compacting':
            return self.get_snapshot()
        event = self._find_active_compact_event()
        if event and (event.payload or {}).get('state') == 'streaming':
            self._patch_compact_progress(event, {
                'state': 'cancelled',
                'message': _("Compaction cancelled by user."),
            })
        self.write({'state': 'done', 'error_message': False})
        self._publish_event('state', {'state': 'done'})
        return self.get_snapshot()

    def undo_to_event(self, event_id):
        if self.state in ('running', 'compacting'):
            raise UserError(_(
                "Cannot rewind while the session is running."
            ))
        if self.state == 'waiting':
            raise UserError(_(
                "Cannot rewind while the session is waiting for input."
            ))
        target = self._resolve_event(event_id)
        cut_index = self._conversation_cut_index(target)
        stale = self.env['muk_ai.session.event'].sudo().search([
            ('session_id', '=', self.id),
            ('sequence', '>=', target.sequence),
        ])
        if stale:
            stale.unlink()
        new_conv = list(self.conversation or [])[:cut_index]
        self.write({
            'conversation': new_conv,
            'pending_ask': False,
            'last_text': False,
            'error_message': False,
            'state': 'done' if new_conv else 'new',
        })
        self._publish_event('state', {'state': self.state})
        return self.get_snapshot()

    def fork_at_event(self, event_id):
        if self.state in ('running', 'compacting'):
            raise UserError(_(
                "Cannot fork while the session is running."
            ))
        target = self._resolve_event(event_id)
        cut_index = self._conversation_cut_index_for_fork(target)
        new_conv = list(self.conversation or [])[:cut_index]
        fork = self.copy({
            'name': _("%s (fork)", self.name),
            'conversation': new_conv,
            'state': 'done' if new_conv else 'new',
            'pending_ask': False,
            'last_text': False,
            'error_message': False,
            'iteration_count': 0,
            'attachment_ids': [(5, 0, 0)],
            'event_ids': [(5, 0, 0)],
            'pending_ids': [(5, 0, 0)],
        })
        source_events = self.env['muk_ai.session.event'].sudo().search([
            ('session_id', '=', self.id),
            ('sequence', '<=', target.sequence),
        ], order='sequence, id')
        for src in source_events:
            self.env['muk_ai.session.event'].sudo().create({
                'session_id': fork.id,
                'sequence': src.sequence,
                'kind': src.kind,
                'payload': src.payload,
                'at': src.at,
            })
        return fork.id

    def upload_attachments(self, files):
        attachments = self.env['ir.attachment'].sudo()
        created = self.env['ir.attachment']
        for entry in files or []:
            created |= attachments._ai_create_from_upload(
                entry.get('filename'),
                entry.get('mimetype'),
                entry.get('data_b64'),
                res_id=self.id,
            )
        if created:
            self.sudo().write({'attachment_ids': [(4, aid) for aid in created.ids]})
        return [a._ai_describe() for a in created]

    def discard_attachments(self, attachment_ids):
        if attachment_ids:
            attachments = self.env['ir.attachment'].browse([
                int(aid) for aid in attachment_ids
            ])
            orphans = attachments.exists().filtered(
                lambda attachment: (
                    attachment.res_model == 'muk_ai.session'
                    and attachment.res_id == self.id
                ),
            )
            self.sudo().write({
                'attachment_ids': [(3, aid) for aid in attachments.ids],
            })
            if orphans:
                orphans.unlink()
        return True

    def set_view_context(self, payload):
        kind = payload.get('kind') if isinstance(payload, dict) else None
        self._write_view_context(
            None if payload is None or kind == 'none'
            else clean_view_context_payload(kind, payload)
        )
        return self.get_snapshot()

    def unpin_view_context(self):
        self._write_view_context(None)
        self._append_event({
            'kind': 'command',
            'name': '/unpin',
            'message': _("View context cleared."),
        })
        return self.get_snapshot()

    def set_approval_mode(self, mode):
        if mode and mode not in ('ask', 'off'):
            raise UserError(_("Unknown approval mode %(mode)r.", mode=mode))
        self.write({'override_approval_mode': mode or False})
        self._publish_event('state', {'state': self.state})
        return self.get_snapshot()

    def approve_tool(self):
        pending = self._require_pending_approval()
        self._record_approval_audit(
            decision='approved',
            call={
                'name': pending.get('name'),
                'arguments': pending.get('arguments'),
            },
            risk=pending.get('risk') or {},
        )
        self._resume_tool_round(pending, approved=True)
        if self.state == 'running':
            self._trigger_worker()
        return self.get_snapshot()

    def approve_for_session(self):
        pending = self._require_pending_approval()
        risk = pending.get('risk') or {}
        if signature := risk.get('signature'):
            self.approved_signatures = [
                *(self.approved_signatures or []),
                signature,
            ]
        self._record_approval_audit(
            decision='approved_session',
            call={
                'name': pending.get('name'),
                'arguments': pending.get('arguments'),
            },
            risk=risk,
        )
        self._resume_tool_round(pending, approved=True)
        if self.state == 'running':
            self._trigger_worker()
        return self.get_snapshot()

    def reject_tool(self, reason=None):
        pending = self._require_pending_approval()
        reason = (reason or '').strip() or _("User rejected the call.")
        self._record_approval_audit(
            decision='rejected',
            call={
                'name': pending.get('name'),
                'arguments': pending.get('arguments'),
            },
            risk=pending.get('risk') or {},
            reject_reason=reason,
        )
        self._resume_tool_round(
            pending, approved=False, reject_reason=reason
        )
        if self.state == 'running':
            self._trigger_worker()
        return self.get_snapshot()

    # ----------------------------------------------------------
    # Actions
    # ----------------------------------------------------------

    def action_open(self):
        self.ensure_one()
        if self.user_id.id != self.env.uid:
            AccessError(_(
                "Only the session owner can continue this chat."
            ))
        return {
            'type': 'ir.actions.client',
            'tag': 'muk_ai.chat',
            'name': self.name or _("AI Chat"),
            'params': {'session_id': self.id},
        }

    def action_stop(self):
        self.ensure_one()
        if self.user_id.id != self.env.uid and not self.env.is_admin():
            AccessError(_(
                "Only the session owner or an administrator can stop this session."
            ))
        if self.state not in ('done', 'error', 'stopped'):
            self.write({'state': 'stopped', 'pending_ask': False})
            self._publish_event('state', {'state': 'stopped'})
        return self.get_snapshot()

    # ----------------------------------------------------------
    # Compute
    # ----------------------------------------------------------

    @api.depends('agent_id', 'agent_id.model_id', 'agent_id.model_id.context_window')
    def _compute_context_window(self):
        for record in self:
            record.context_window = record._resolve_context_window()

    @api.depends('override_approval_mode', 'agent_id', 'agent_id.approval_mode')
    def _compute_effective_approval_mode(self):
        for record in self:
            record.effective_approval_mode = record._effective_approval_mode()

    @api.depends(
        'pending_ids',
        'pending_ids.queued_at',
        'pending_ids.content',
        'pending_ids.attachment_ids',
    )
    def _compute_pending_user_messages(self):
        for record in self:
            record.pending_user_messages = record._serialize_pending()

    @api.depends('event_ids', 'event_ids.sequence', 'event_ids.payload')
    def _compute_display_events(self):
        for record in self:
            record.display_events = (
                record.fetch_events(limit=100)['events']
                if record.id else []
            )

    # ----------------------------------------------------------
    # ORM
    # ----------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        self._check_rate_limit(batch_size=len(vals_list) or 1)
        records = super().create(vals_list)
        for record in records:
            with suppress(Exception):
                record._bus_send('muk_ai.session_state', {
                    'session_id': record.id,
                    'name': record.name,
                    'state': record.state,
                })
        return records

    # ----------------------------------------------------------
    # Cron
    # ----------------------------------------------------------

    @api.model
    def _cron_run_pending_sessions(self):
        self._sweep_orphan_sessions()
        if candidates := self._find_pending_session_ids():
            self._commit_safe()
            for sid in candidates:
                if self._process_session_in_worker(sid):
                    break
            if len(candidates) > 1:
                self._trigger_worker()

    @api.model
    def _sweep_orphan_sessions(self):
        threshold = fields.Datetime.now() - timedelta(
            seconds=WORKER_STALE_THRESHOLD
        )
        candidates = self.sudo().search([
            ('state', 'in', ('running', 'compacting')),
            ('write_date', '<', threshold),
            '|',
                ('claimed_at', '=', False),
                ('claimed_at', '<', threshold),
        ])
        for session in candidates:
            if not self._try_session_xact_lock(session.id):
                continue
            try:
                with self.env.cr.savepoint():
                    session.write({
                        'state': 'error',
                        'error_message': _(
                            "Worker abandoned the session — please retry."
                        ),
                    })
                session._publish_event('state', {
                    'state': 'error',
                    'error': session.error_message,
                })
            except psycopg2.errors.SerializationFailure:
                continue

    @api.model
    def _session_worker_crons(self):
        return self.env['ir.cron'].sudo().search([
            ('state', '=', 'ai_session'),
            ('active', '=', True),
        ])

    @api.model
    def _active_worker_count(self):
        return max(1, len(self._session_worker_crons()))

    @api.model
    def _find_pending_session_ids(self, limit=None):
        if limit is None:
            limit = self._active_worker_count()
        self.env.cr.execute(SQL(
            """
            SELECT id FROM muk_ai_session
            WHERE state IN ('running', 'compacting')
            ORDER BY write_date
            LIMIT %s
            """,
            limit,
        ))
        return [row[0] for row in self.env.cr.fetchall()]

    @api.model
    def _process_session_in_worker(self, session_id):
        processed = False
        with self.pool.cursor() as cr:
            cr.execute(SQL(
                "SELECT pg_try_advisory_lock(%s, %s)",
                ADVISORY_LOCK_NAMESPACE,
                session_id,
            ))
            if cr.fetchone()[0]:
                try:
                    env_su = api.Environment(cr, SUPERUSER_ID, {})
                    session_su = env_su['muk_ai.session'].browse(session_id)
                    if (
                        session_su.exists()
                        and session_su.state in ('running', 'compacting')
                    ):
                        env = api.Environment(
                            cr,
                            session_su.user_id.id,
                            session_su.user_context or {},
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
                        except StreamCancelled:
                            cr.rollback()
                        except Exception as error:
                            cr.rollback()
                            self._mark_session_error(
                                session_id, str(error)
                            )
                        processed = True
                finally:
                    with suppress(Exception):
                        cr.execute(SQL(
                            "SELECT pg_advisory_unlock(%s, %s)",
                            ADVISORY_LOCK_NAMESPACE,
                            session_id,
                        ))
                        cr.fetchone()
        return processed

    @api.model
    def _mark_session_error(self, session_id, message):
        with self.pool.cursor() as cr:
            session = (
                api.Environment(cr, SUPERUSER_ID, {})['muk_ai.session']
                .browse(session_id)
            )
            if session.exists():
                session.write({
                    'state': 'error',
                    'error_message': message,
                })
                session._publish_event('state', {
                    'state': 'error',
                    'error': message,
                })
                cr.commit()

    def _capture_user_context(self):
        safe = {}
        for key, value in (self.env.context or {}).items():
            try:
                json.dumps(value)
            except (TypeError, ValueError):
                continue
            safe[key] = value
        return safe

    def _trigger_worker(self):
        self.sudo().write({
            'user_context': self._capture_user_context(),
        })
        if modules.module.current_test:
            for session in self:
                if session.state == 'compacting':
                    session._do_compact()
                elif session.state == 'running':
                    session._run_to_completion()
            return
        if crons := self._session_worker_crons():
            random.choice(crons)._trigger()
