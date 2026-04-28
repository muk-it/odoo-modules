import base64
import json
import logging
import re
import time

from datetime import timedelta

import psycopg2
import urllib3

from markupsafe import Markup, escape

from odoo import SUPERUSER_ID, _, api, fields, models, modules
from odoo.exceptions import UserError
from odoo.tools.rendering_tools import parse_inline_template, render_inline_template

from odoo.addons.muk_ai.tools import (
    ALLOWED_MIMETYPES,
    ASK_USER_TOOL,
    ATTACHMENT_REF_RE,
    INLINE_IMAGE_RE,
    TERMINATING_TOOLS,
    URL_REF_RE,
    StreamCancelled,
    build_tool_call_output,
    clean_view_context_payload,
    fetch_url,
    sanitize_json_schema,
    with_ui_ctx,
)
from odoo.addons.muk_ai.tools.limits import (
    DEFAULT_CONTEXT_WINDOW,
    MAX_ITERATIONS,
    MAX_TOOL_CALLS_PER_ROUND,
    MAX_WALLCLOCK_SECONDS,
)

_logger = logging.getLogger(__name__)

ADVISORY_LOCK_NAMESPACE = 0x4D554B41
WORKER_HEARTBEAT_INTERVAL = 5
WORKER_STALE_THRESHOLD = 60
WORKER_CRON_COUNT = 4
ATTACHMENT_REF_MAX_BYTES = 4 * 1024 * 1024


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
    def _get_system_prompt(self):
        return self.env['muk_ai.agent']._get_default().system_prompt

    def _effective_system_prompt(self):
        raw = (
            self.agent_id.system_prompt
            if self.agent_id and self.agent_id.system_prompt
            else self._get_system_prompt()
        )
        return self._render_system_prompt(raw or '')

    def _render_system_prompt(self, raw):
        if not raw:
            return ''
        raw = raw.strip()
        if '{{' not in raw:
            return raw
        try:
            return render_inline_template(
                parse_inline_template(raw),
                self._render_system_prompt_eval_context(),
            )
        except Exception:
            _logger.exception(
                "muk_ai: failed to render system prompt template "
                "for agent %(agent)s; falling back to raw",
                {'agent': (self.agent_id.id, self.agent_id.name) if self.agent_id else '(default)'},
            )
            return raw

    def _render_system_prompt_eval_context(self):
        return {
            'user': self.env.user,
            'company': self.env.company,
            'ctx': self.env.context,
            'env': self.env,
            'today': fields.Date.context_today(self).isoformat(),
            'approval_mode': (
                self._effective_approval_mode()
                if self and self.id else 'ask'
            ),
        }

    def _effective_model_record(self):
        if self.agent_id and self.agent_id.model_id:
            return self.agent_id.model_id
        return self.env['muk_ai.provider']._get_default().default_model_id

    def _effective_provider(self):
        if record := self._effective_model_record():
            return record.provider_id
        return self.env['muk_ai.provider']._get_default()

    def _effective_model(self):
        record = self._effective_model_record()
        return record.technical_name if record else None

    def _resolve_context_window(self):
        record = self._effective_model_record()
        return (record.context_window if record else 0) or DEFAULT_CONTEXT_WINDOW

    def _effective_approval_mode(self):
        if self.override_approval_mode:
            return self.override_approval_mode
        if self.agent_id and self.agent_id.approval_mode:
            return self.agent_id.approval_mode
        return 'ask'

    # ----------------------------------------------------------
    # Helper Inputs
    # ----------------------------------------------------------

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
        inputs = [
            {
                'role': 'system',
                'content': [{
                    'type': 'input_text',
                    'text': self._effective_system_prompt()
                }],
            },
        ]
        if user_entry := self._build_user_entry(user_message, attachments):
            inputs.append(user_entry)
        return inputs

    def _user_message_log(self, user_message, attachments):
        return {
            'kind': 'user_message',
            'content': user_message or '',
            'attachments': [a._ai_describe() for a in attachments],
        }

    def _get_tool_schema(self):
        tool_env = self.env(context={
            **self.env.context,
            **self._tool_dispatch_context(),
        })
        tools = list(tool_env['muk_mcp.tool'].sudo().get_tools(
            registry='odoo',
        ))
        if self._effective_approval_mode() != 'off':
            tools.append(ASK_USER_TOOL)
        if self.agent_id:
            tools = self.agent_id.apply_tool_filter(
                tools
            )
        result = []
        for tool in tools:
            schema = (
                 tool.get('inputSchema') or
                 {'type': 'object', 'properties': {}}
            )
            result.append({
                'type': 'function',
                'name': tool['name'],
                'description': tool.get('description') or '',
                'parameters': sanitize_json_schema(schema),
                'strict': False,
            })
        return result

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

    def _notify_state_transition(self, payload):
        new_state = (payload or {}).get('state')
        if new_state not in ('done', 'waiting', 'error'):
            return
        ask = (payload or {}).get('ask') or self.pending_ask or {}
        ask_kind = ask.get('kind') if isinstance(ask, dict) else None
        title, message = self._notification_summary(new_state, payload, ask_kind)
        try:
            self._bus_send('muk_ai.session_notification', {
                'session_id': self.id,
                'session_name': self.name,
                'state': new_state,
                'ask_kind': ask_kind,
                'title': title,
                'message': message,
            })
        except Exception:
            _logger.warning(
                "muk_ai: failed to send session notification bus event",
                exc_info=True,
            )
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
            return (
                _("AI session error"),
                _(
                    "Session “%(name)s” stopped: %(reason)s",
                    name=name,
                    reason=self._short_error_reason(
                        (payload or {}).get('error') or self.error_message or '',
                    ),
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
        if not raw:
            return _("unknown error")
        text = raw.strip()
        if len(text) > 8192:
            text = text[:8192]
        match = re.search(r'\{.*\}', text, flags=re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(0))
                err = data.get('error') if isinstance(data, dict) else None
                if isinstance(err, dict) and err.get('message'):
                    text = err['message']
                elif data.get('message'):
                    text = data['message']
            except (ValueError, AttributeError):
                pass
        text = ' '.join(text.split())
        if len(text) > 200:
            text = text[:197] + '…'
        return text

    def _post_inbox_notification(self, title, message):
        partner = self.user_id.partner_id
        if not partner:
            return
        link = Markup('<p><a href="/odoo/ai?session_id=%s">%s</a></p>') % (
            self.id, _("Open Chat"),
        )
        body = Markup('<p>%s</p>') % escape(message) + link
        try:
            new_message = self.env['mail.thread'].sudo().message_notify(
                partner_ids=partner.ids,
                subject=title,
                body=body,
            )
            if new_message:
                new_message.sudo().muk_ai_session_id = self.id
        except Exception:
            _logger.warning(
                "muk_ai: failed to post inbox notification for session %s",
                self.id, exc_info=True,
            )

    # ----------------------------------------------------------
    # Helper State
    # ----------------------------------------------------------

    def _append_log(self, entry):
        stamped = entry if 'at' in entry else {
            **entry,
            'at': fields.Datetime.now().isoformat(),
        }
        kind = stamped.get('kind') or ''
        events = self.env['muk_ai.session.event'].sudo()
        for _attempt in range(5):
            self.env.cr.execute(
                "SELECT COALESCE(MAX(sequence), -1) + 1 "
                "FROM muk_ai_session_event WHERE session_id = %s",
                [self.id],
            )
            sequence = self.env.cr.fetchone()[0]
            try:
                with self.env.cr.savepoint():
                    events.create({
                        'session_id': self.id,
                        'sequence': sequence,
                        'kind': kind,
                        'payload': stamped,
                        'at': fields.Datetime.now(),
                    })
                break
            except psycopg2.errors.UniqueViolation:
                continue
        self._publish_event('log', stamped)

    def _extend_conversation(self, items):
        self.conversation = [*(self.conversation or []), *(items or [])]

    def _resolve_attachments(self, attachment_ids):
        requested = self.env['ir.attachment'].browse(
            [int(aid) for aid in attachment_ids or []]
        )
        attachments = requested.exists()
        if attachments != requested:
            raise UserError(_(
                "One or more attachments could not be found.",
            ))
        attachments._ai_validate()
        if new := attachments - self.attachment_ids:
            self.sudo().write({'attachment_ids': [(4, a.id) for a in new]})
            new.sudo().write({'res_model': 'muk_ai.session', 'res_id': self.id})
        return attachments

    def _enqueue_user_turn(
        self,
        user_message,
        attachments,
        extend=True
    ):
        if extend:
            user_entry = self._build_user_entry(
                user_message, attachments
            )
            if user_entry:
                self._extend_conversation([user_entry])
        if user_message or attachments:
            self._append_log(self._user_message_log(
                user_message, attachments
            ))
        self.write({'state': 'running', 'error_message': False})
        self._publish_event('state', {'state': 'running'})

    def _record_tool_result(
        self,
        outputs,
        call_id,
        name,
        output_result,
        log_result=None
    ):
        outputs.append(build_tool_call_output(
            call_id, output_result
        ))
        self._append_log({
            'kind': 'tool_result',
            'name': name,
            'result': (
                output_result
                if log_result is None else log_result
            ),
            'call_id': call_id,
        })

    def _persist_synthetic_tool_log(self, call, result, status):
        arguments = call.get('arguments') or {}
        try:
            request_data = json.dumps(arguments)
        except (TypeError, ValueError):
            request_data = str(arguments)
        try:
            response_data = json.dumps(result)
        except (TypeError, ValueError):
            response_data = str(result)
        error_message = None
        if isinstance(result, dict):
            error_message = result.get('error') or result.get('reason')
        model_name = (
            arguments.get('model')
            if isinstance(arguments, dict) else None
        ) or ''
        self.env['muk_mcp.log'].sudo().create({
            'method': 'tools/call',
            'tool_name': call.get('name') or '',
            'model_name': model_name,
            'user_id': self.env.uid,
            'status': status,
            'duration_ms': 0,
            'request_data': request_data,
            'response_data': response_data,
            'error_message': error_message,
            'source': 'chat',
            'session_id': self.id,
        })

    def _commit_safe(self):
        if not modules.module.current_test:
            self.env.cr.commit()

    def _transition_state(self, state, error=None):
        self.write(
            {'state': state} |
            ({'error_message': error} if error else {})
        )
        self._publish_event(
            'state',
            {'state': state} | ({'error': error} if error else {})
        )

    def _recover_if_stuck(self, idle_seconds=WORKER_STALE_THRESHOLD):
        if self.state not in ('running', 'compacting'):
            return False
        reference = self.claimed_at or self.write_date
        if not reference:
            return False
        idle = (fields.Datetime.now() - reference).total_seconds()
        if idle < idle_seconds:
            return False
        pending = self.pending_ids
        had_queue = bool(pending)
        if pending:
            pending.unlink()
            self.invalidate_recordset(['pending_ids'])
        self.write({
            'state': 'error',
            'error_message': _(
                "Previous turn timed out after %(idle)s seconds with no "
                "activity. Session reset.",
                idle=int(idle),
            ),
        })
        self._publish_event('state', {
            'state': 'error',
            'error': self.error_message,
        })
        if had_queue:
            self._publish_event('queue', {'pending': []})
        return True

    def _unified_log(self, limit=500):
        if not self.id:
            return []
        events = self.env['muk_ai.session.event'].sudo().search(
            [('session_id', '=', self.id)],
            order='sequence, id',
            limit=limit,
        )
        out = []
        for ev in events:
            payload = dict(ev.payload or {})
            payload.setdefault('kind', ev.kind)
            if not payload.get('at') and ev.at:
                payload['at'] = ev.at.isoformat()
            out.append(payload)
        return out

    def get_snapshot(self):
        self.ensure_one()
        return self._get_snapshot()

    def _get_snapshot(self):
        return {
            'id': self.id,
            'tool_log': self._unified_log(),
            'conversation': self.conversation or [],
            'error_message': self.error_message,
            'last_text': self.last_text,
            'attachments': [a._ai_describe() for a in self.attachment_ids],
            'total_input_cost': self.total_input_cost,
            'total_output_cost': self.total_output_cost,
            'pending_user_messages': self._serialize_pending(),
            **self._state_metrics(),
        }

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
                    "Rate limit reached (%(count)s sessions in the last minute, "
                    "max %(limit)s). Please slow down.",
                    count=count, limit=limit,
                ))

    # ----------------------------------------------------------
    # Helper Tool Dispatch
    # ----------------------------------------------------------

    def _tool_dispatch_context(self):
        return {
            'muk_mcp_session_id': self.id,
        }

    def _dispatch_tool_call(self, name, arguments, call_id):
        enforce_scope = (
            'read'
            if self.agent_id and self.agent_id.read_only
            else None
        )
        arguments, resolved_refs = self._resolve_value_refs(
            arguments
        )
        try:
            tool_env = self.env(context={
                **self.env.context,
                **self._tool_dispatch_context(),
            })
            text, _info = tool_env['muk_mcp.tool']._call(
                name,
                arguments,
                tool_env,
                enforce_scope=enforce_scope,
            )
        except UserError as error:
            return {'error': str(error)}, False
        except Exception as error:
            _logger.exception("muk_ai: tool %s raised", name)
            return {'error': str(error)}, False
        self._maybe_publish_ui_action(
            text, name, call_id
        )
        if resolved_refs:
            previews = '\n\n'.join(
                f'![image set]({ref["preview_url"]})'
                for ref in resolved_refs if ref.get('preview_url')
            )
            if previews:
                if isinstance(text, str):
                    text = f'{text}\n\n{previews}'
                elif isinstance(text, dict):
                    text = {
                        **text,
                        'image_previews': [
                            r['preview_url']
                            for r in resolved_refs
                            if r.get('preview_url')
                        ],
                    }
        return text, True

    def _maybe_publish_ui_action(self, text, name, call_id):
        try:
            action = json.loads(text) if isinstance(text, str) else None
        except ValueError:
            action = None
        action_type = action.get('type') if isinstance(action, dict) else None
        if isinstance(action_type, str) and action_type.startswith('ir.actions.'):
            self._publish_event('ui_action', {
                'call_id': call_id,
                'name': name,
                'action': action
            })
            if name in TERMINATING_TOOLS:
                self._apply_ui_action(name, action)

    # ----------------------------------------------------------
    # Helper View Context
    # ----------------------------------------------------------

    def _apply_ui_action(self, tool_name, action):
        if payload := self._view_context_from_action(
            tool_name, action
        ):
            self._write_view_context(payload)

    def _view_context_from_action(self, tool_name, action):
        if (
            not isinstance(action, dict) or
            not (res_model := action.get('res_model'))
        ):
            return None
        wants_record = (
            tool_name == 'open_record' or
            action.get('view_mode') == 'form'
        )
        if wants_record:
            if not (res_id := action.get('res_id')):
                return None
            record = self.env[res_model].sudo().browse(
                int(res_id)
            )
            return {
                'kind': 'record',
                'model': res_model,
                'id': int(res_id),
                'display_name': (
                    record.exists().display_name or
                    str(res_id)
                ),
            }
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

    def _enrich_view_context(self, payload):
        return payload

    def _write_view_context(self, payload):
        if payload:
            payload = self._enrich_view_context(payload)
        self.write({'view_context': payload or False})
        self._publish_event('view_context', {
            'view_context': payload or None
        })

    # ----------------------------------------------------------
    # Helper Streaming
    # ----------------------------------------------------------

    def _check_cancelled(self, buffer_state):
        last = buffer_state.get('last_state_check', 0)
        if (now := time.monotonic()) - last >= 0.3:
            buffer_state['last_state_check'] = now
            last_beat = buffer_state.get('last_heartbeat', 0)
            if now - last_beat >= WORKER_HEARTBEAT_INTERVAL:
                buffer_state['last_heartbeat'] = now
                self.claimed_at = fields.Datetime.now()
                self.invalidate_recordset(['state'])
                if self.state == 'stopped':
                    if buffer_state.get('full_text'):
                        self._persist_partial(buffer_state)
                        buffer_state['full_text'] = ''
                        self._commit_safe()
                    raise StreamCancelled()

    def _on_stream_delta(self, kind, payload, buffer_state):
        self._check_cancelled(buffer_state)
        if kind == 'text':
            if delta := (payload or {}).get('delta') or '':
                buffer_state['full_text'] = (
                    buffer_state.get('full_text', '') + delta
                )
                self._coalesce_and_emit(
                    buffer_state,
                    'text',
                    'last_text_flush',
                    delta,
                    'text_delta',
                )
        elif kind == 'reasoning':
            if delta := (payload or {}).get('delta') or '':
                self._coalesce_and_emit(
                    buffer_state,
                    'reasoning',
                    'last_reasoning_flush',
                    delta,
                    'reasoning_delta',
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
        extra=None,
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
            self.last_text = text
            self._append_log({
                'kind': 'text',
                'content': text
            })
            self._extend_conversation([{
                'type': 'message',
                'role': 'assistant',
                'content': [{
                    'type': 'output_text',
                    'text': text
                }],
            }])

    def _flush_stream_buffer(self, buffer_state):
        self._flush_text_buffer(buffer_state)
        if flushed := buffer_state.get('reasoning'):
            buffer_state['reasoning'] = ''
            self._publish_event('reasoning_delta', {'delta': flushed})
        for key in list(buffer_state.keys()):
            if (
                key.startswith('tool_args_') and
                not key.endswith('_last')
            ):
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
                inputs=with_ui_ctx(self.conversation, self.view_context),
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
        if not text or 'data:image/' not in text:
            return text
        cache = cache if cache is not None else {}

        def _replace(match):
            alt = match.group(1) or 'generated.png'
            mimetype = match.group(2)
            b64 = re.sub(r'\s+', '', match.group(3))
            cached = cache.get(b64)
            if cached:
                attachment_id = cached
            else:
                try:
                    attachment = self.env['ir.attachment'].sudo()._ai_create_from_upload(
                        alt or 'generated.png',
                        mimetype,
                        b64,
                        res_id=self.id,
                    )
                except UserError as error:
                    _logger.warning("muk_ai: rejected inline image attachment: %s", error)
                    return match.group(0)
                except Exception:
                    _logger.exception("muk_ai: failed to persist inline image attachment")
                    return match.group(0)
                attachment_id = attachment.id
                cache[b64] = attachment_id
            return (
                f'![{alt}](/web/image/{attachment_id}) '
                f'_(attachment {attachment_id} — to set on a record use '
                f'`image_1920="@attachment:{attachment_id}"`)_'
            )

        return INLINE_IMAGE_RE.sub(_replace, text)

    def _persist_inline_images_in_carry(self, items, cache):
        out = []
        for item in items or []:
            if not isinstance(item, dict):
                out.append(item)
                continue
            content = item.get('content')
            if not isinstance(content, list):
                out.append(item)
                continue
            new_content = []
            for chunk in content:
                if isinstance(chunk, dict) and isinstance(chunk.get('text'), str) and 'data:image/' in chunk['text']:
                    new_content.append({**chunk, 'text': self._persist_inline_images(chunk['text'], cache=cache)})
                else:
                    new_content.append(chunk)
            out.append({**item, 'content': new_content})
        return out

    def _resolve_value_refs(self, arguments):
        refs = []
        if not isinstance(arguments, dict):
            return arguments, refs

        def _resolve(value):
            if isinstance(value, str):
                if m := ATTACHMENT_REF_RE.match(value):
                    attachment = self.env['ir.attachment'].sudo().browse(int(m.group(1))).exists()
                    if attachment and attachment.datas:
                        if attachment.file_size > ATTACHMENT_REF_MAX_BYTES:
                            _logger.warning(
                                "muk_ai: refused @attachment:%s — size %s exceeds cap %s",
                                attachment.id, attachment.file_size, ATTACHMENT_REF_MAX_BYTES,
                            )
                            return value
                        if attachment.mimetype and attachment.mimetype not in ALLOWED_MIMETYPES:
                            _logger.warning(
                                "muk_ai: refused @attachment:%s — mimetype %s not allowed",
                                attachment.id, attachment.mimetype,
                            )
                            return value
                        refs.append({'kind': 'attachment', 'preview_url': f'/web/image/{attachment.id}'})
                        return attachment.datas.decode()
                    return value
                if m := URL_REF_RE.match(value):
                    url = m.group(1)
                    try:
                        content = fetch_url(self.env, url)
                    except (UserError, urllib3.exceptions.HTTPError) as exc:
                        _logger.warning("muk_ai: refused @url:%s — %s", url, exc)
                        return value
                    refs.append({'kind': 'url', 'preview_url': url})
                    return base64.b64encode(content).decode()
                return value
            if isinstance(value, dict):
                return {k: _resolve(v) for k, v in value.items()}
            if isinstance(value, list):
                return [_resolve(v) for v in value]
            return value

        return _resolve(arguments), refs

    def _accrue_round_payload(self, payload):
        usage = payload.get('usage') or {}
        round_input_tokens = usage.get('input_tokens')
        self.write({
            'iteration_count': self.iteration_count + 1,
            'total_input_tokens': self.total_input_tokens + (round_input_tokens or 0),
            'total_output_tokens': self.total_output_tokens + usage.get('output_tokens', 0),
            'last_input_tokens': self.last_input_tokens if round_input_tokens is None else round_input_tokens,
            **self._accrue_cost_deltas(usage),
        })
        image_cache = {}
        text = payload.get('text')
        if text and 'data:image/' in text:
            text = self._persist_inline_images(text, cache=image_cache)
            payload['text'] = text
        if text:
            self.last_text = text
            self._append_log({'kind': 'text', 'content': text})
        carry = self._persist_inline_images_in_carry(
            payload.get('carry_inputs') or [], image_cache,
        )
        self._extend_conversation(carry)

    def _finalize_round(self, payload):
        if payload.get('text'):
            self._transition_state('done')
        else:
            self._transition_state('error', error=_("AI returned no output."))

    def _skip_reason(self, has_ask_user, has_terminating):
        if has_ask_user:
            return 'skipped: ask_user pending, call again after user answer'
        if has_terminating:
            return 'skipped: terminating tool already ran; emit a short summary and stop'
        return None

    def _log_tool_call(self, call):
        self._append_log({
            'kind': 'tool_call',
            'name': call['name'],
            'arguments': call['arguments'],
            'call_id': call['call_id'],
        })

    def _skip_tool_call(self, outputs, call, reason, log_result=None):
        result = {'error': reason}
        self._persist_synthetic_tool_log(call, result, 'denied')
        self._record_tool_result(
            outputs,
            call['call_id'],
            call['name'],
            result,
            log_result=log_result,
        )

    def _register_ask_user(self, call):
        args = call['arguments'] or {}
        question = args.get('question')
        options = args.get('options')
        resolution = args.get('resolution') or 'text'
        preview = args.get('preview') or None
        self.pending_ask = {
            'kind': 'question',
            'call_id': call['call_id'],
            'text': question,
            'options': options,
            'resolution': resolution,
            'preview': preview,
        }
        self._append_log({
            'kind': 'ask_user',
            'call_id': call['call_id'],
            'text': question,
            'options': options,
            'resolution': resolution,
            'preview': preview,
        })

    def _execute_tool_call(self, call, tool_calls, outputs, index, has_terminating):
        gate = self._check_approval_gate(call['name'], call['arguments'])
        if gate['action'] == 'pause':
            self._enter_waiting_approval(
                call, tool_calls, outputs, index, has_terminating, gate,
            )
            return None
        self._log_tool_call(call)
        if gate['action'] == 'auto_approved':
            self._record_approval_audit(
                decision='auto_approved', call=call, risk=gate['risk'],
            )
        result, ok = self._dispatch_tool_call(
            call['name'], call['arguments'], call['call_id'],
        )
        self._record_tool_result(outputs, call['call_id'], call['name'], result)
        return ok and call['name'] in TERMINATING_TOOLS

    def _process_tool_round(self, tool_calls, outputs, start_index, has_terminating=False):
        has_ask_user = any(c.get('name') == 'ask_user' for c in tool_calls)
        wait_for_user, paused = False, False
        for index in range(start_index, len(tool_calls)):
            call = tool_calls[index]
            if index >= MAX_TOOL_CALLS_PER_ROUND:
                self._log_tool_call(call)
                self._skip_tool_call(
                    outputs, call, 'tool_call_limit_exceeded',
                    log_result={'error': 'tool_call_limit_exceeded'},
                )
                continue
            if call.get('_parse_error'):
                self._log_tool_call(call)
                self._skip_tool_call(outputs, call, call['_parse_error'])
                continue
            if call['name'] == 'ask_user':
                self._register_ask_user(call)
                wait_for_user = True
                continue
            if skip := self._skip_reason(has_ask_user, has_terminating):
                self._log_tool_call(call)
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
                    'ask': self.pending_ask,
                })
        return None if paused or wait_for_user else has_terminating

    def _run_to_completion(self, has_terminating=False):
        deadline = time.monotonic() + MAX_WALLCLOCK_SECONDS
        while True:
            self._run_iterations(has_terminating=has_terminating, deadline=deadline)
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
        if deadline is None:
            deadline = time.monotonic() + MAX_WALLCLOCK_SECONDS
        provider, model = self._effective_provider(), self._effective_model()
        agent, tool_schema = self.agent_id, self._get_tool_schema()
        for _iteration in range(MAX_ITERATIONS):
            if self.state != 'running':
                return
            if time.monotonic() > deadline:
                self._transition_state('error', error=_(
                    "Wallclock cap reached (%(s)s s). Send a new message to continue.",
                    s=MAX_WALLCLOCK_SECONDS,
                ))
                return
            self.invalidate_recordset(['pending_ids'])
            if self.pending_ids and self._drain_pending_message():
                has_terminating = False
            schema, round_agent = (None, None) if has_terminating else (tool_schema, agent)
            try:
                payload = self._stream_provider_round(provider, schema, model, round_agent)
            except StreamCancelled:
                self.env.cr.rollback()
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
            result = self._process_tool_round(tool_calls, [], 0, has_terminating=has_terminating)
            if result is None:
                return
            has_terminating = has_terminating or result
        if self.state == 'running':
            self._transition_state('error', error=_("Maximum iterations reached."))

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
        return self._get_snapshot()

    def cancel_queued(self, index):
        pending = self.pending_ids
        if 0 <= index < len(pending):
            pending[index].unlink()
            self.invalidate_recordset(['pending_ids'])
            self._publish_event(
                'queue', {'pending': self._serialize_pending()},
            )
        return self._get_snapshot()

    def _drain_pending_message(self):
        pending = self.pending_ids
        if not pending:
            return False
        contents = [p.content or '' for p in pending]
        attachment_ids = [
            aid for p in pending for aid in (p.attachment_ids or [])
        ]
        combined = '\n\n'.join(c for c in contents if c.strip())
        pending.unlink()
        self.invalidate_recordset(['pending_ids'])
        self._publish_event('queue', {'pending': []})
        attachments = self._resolve_attachments(attachment_ids)
        self._enqueue_user_turn(combined, attachments)
        return True

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
        preview = (
            self.env['muk_ai.approval']._build_preview(
                call['name'], call['arguments']
            ) or {}
        )
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
        self._append_log({
            'kind': 'ask_user',
            'call_id': call['call_id'],
            'text': risk.get('reason') or '',
            'resolution': 'yesno',
            'preview': preview,
        })
        self.write({
            'state': 'waiting',
            'pending_ask': pending,
        })
        self._publish_event('state', {
            'state': 'waiting',
            'ask': pending,
        })

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
        resume_index = paused.get('resume_index', 0)
        tool_calls = list(paused.get('tool_calls') or [])
        has_terminating = bool(paused.get('has_terminating'))
        self._log_tool_call(call)
        if approved:
            result, ok = self._dispatch_tool_call(
                call['name'], call['arguments'], call['call_id'],
            )
            if ok and call['name'] in TERMINATING_TOOLS:
                has_terminating = True
        else:
            result = {
                'error': 'rejected_by_user',
                'reason': reject_reason or ''
            }
            self._persist_synthetic_tool_log(call, result, 'denied')
        self._record_tool_result(
            outputs,
            call['call_id'],
            call['name'],
            result
        )
        self.pending_ask = False
        self._transition_state('running')
        self._process_tool_round(
            tool_calls,
            outputs,
            resume_index + 1,
            has_terminating=has_terminating,
        )

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    def dismiss_notifications(self):
        partner = self.env.user.partner_id
        if not partner:
            return False
        messages = self.env['mail.message'].sudo().search([
            ('muk_ai_session_id', 'in', self.ids),
            ('notification_ids.res_partner_id', '=', partner.id),
            ('notification_ids.is_read', '=', False),
        ])
        if messages:
            messages.with_user(self.env.user).set_message_done()
        return True

    def start(self, user_message=None, attachment_ids=None):
        self._recover_if_stuck()
        if self.state not in ('new', 'error', 'stopped'):
            raise UserError(_("Session is not in a startable state."))
        attachments = self._resolve_attachments(attachment_ids)
        if not self.conversation:
            self.conversation = self._build_initial_inputs(user_message, attachments)
            self._enqueue_user_turn(user_message, attachments, extend=False)
        else:
            self._enqueue_user_turn(user_message, attachments)
        self._trigger_worker()
        return self._get_snapshot()

    def answer(self, answer, attachment_ids=None):
        self._recover_if_stuck()
        pending = self.pending_ask or {}
        if self.state != 'waiting' or pending.get('kind') != 'question':
            raise UserError(_("Session is not waiting for user input."))
        question = pending.get('text') or ''
        attachments = self._resolve_attachments(attachment_ids)
        if call_id := pending.get('call_id'):
            self._extend_conversation([
                build_tool_call_output(call_id, {
                    'status': 'answered',
                    'question': question,
                    'answer': answer,
                }),
            ])
            if attachments:
                self._extend_conversation([self._build_user_entry(None, attachments)])
        else:
            followup_text = f'Answer to "{question}": {answer}' if question else answer
            if user_entry := self._build_user_entry(followup_text, attachments):
                self._extend_conversation([user_entry])
        self._append_log({
            'kind': 'answer',
            'question': question,
            'answer': answer,
            'attachments': [a._ai_describe() for a in attachments],
        })
        self.write({
            'state': 'running',
            'pending_ask': False,
        })
        self._publish_event('state', {'state': 'running'})
        self._trigger_worker()
        return self._get_snapshot()

    def send_message(self, user_message, attachment_ids=None):
        self._recover_if_stuck()
        if self.state in ('running', 'compacting'):
            return self.enqueue_message(
                user_message, attachment_ids=attachment_ids,
            )
        if self.state == 'waiting':
            kind = (self.pending_ask or {}).get('kind')
            if kind == 'approval':
                return self.enqueue_message(
                    user_message, attachment_ids=attachment_ids,
                )
            if kind == 'question':
                return self.answer(user_message, attachment_ids=attachment_ids)
        if not self.conversation:
            return self.start(user_message, attachment_ids=attachment_ids)
        attachments = self._resolve_attachments(attachment_ids)
        self._enqueue_user_turn(user_message, attachments)
        self._trigger_worker()
        return self._get_snapshot()

    def regenerate_last_turn(self):
        if self.state in ('running', 'waiting'):
            raise UserError(_(
                "Cannot regenerate while the session is running or waiting.",
            ))
        conv = list(self.conversation or [])
        last_user = None
        for idx in range(len(conv) - 1, -1, -1):
            item = conv[idx]
            if isinstance(item, dict) and item.get('role') == 'user':
                last_user = idx
                break
        if last_user is None:
            raise UserError(_("No user turn to regenerate from."))
        self.conversation = conv[:last_user + 1]
        events = self.env['muk_ai.session.event'].sudo().search(
            [('session_id', '=', self.id)],
            order='sequence, id',
        )
        last_user_event = None
        for ev in reversed(events):
            if ev.kind == 'user_message':
                last_user_event = ev
                break
        if last_user_event is not None:
            stale = events.filtered(
                lambda e: (
                    e.sequence > last_user_event.sequence or
                    (e.sequence == last_user_event.sequence
                     and e.id > last_user_event.id)
                ),
            )
        else:
            stale = events
        if stale:
            stale.sudo().unlink()
        self.write({
            'pending_ask': False,
            'error_message': False,
            'state': 'running',
        })
        self._publish_event('state', {'state': 'running'})
        self._trigger_worker()
        return self._get_snapshot()

    def clear(self):
        if self.state in ('running', 'compacting'):
            raise UserError(_(
                "Cannot clear the conversation while the session is running.",
            ))
        log_entry = {
            'kind': 'command',
            'name': '/clear',
            'message': _("Conversation cleared."),
        }
        if self.pending_ids:
            self.pending_ids.unlink()
            self.invalidate_recordset(['pending_ids'])
        self.event_ids.sudo().unlink()
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
        self._append_log(log_entry)
        self._publish_event('state', {'state': 'new'})
        self._publish_event('queue', {'pending': []})
        return self._get_snapshot()

    def compact(self):
        if self.state in ('running', 'compacting'):
            raise UserError(_("Cannot compact while the session is running. Stop first."))
        if self.state == 'waiting':
            raise UserError(_("Cannot compact while the session is waiting for user input."))
        if not self.conversation:
            raise UserError(_("Nothing to compact yet — the conversation is empty."))
        self.write({'state': 'compacting', 'error_message': False})
        self._publish_event('state', {'state': 'compacting'})
        self._trigger_worker()
        return self._get_snapshot()

    def _do_compact(self):
        try:
            payload = self._effective_provider()._request_responses(
                inputs=list(self.conversation) + [{
                    'role': 'user',
                    'content': [{'type': 'input_text', 'text': (
                        "Summarize this conversation in no more than 500 tokens. "
                        "Preserve key facts, decisions, the user's stated goals, "
                        "and any unresolved questions. Omit pleasantries. Start "
                        "directly with the summary — no preamble."
                    )}],
                }],
                tools_schema=None,
                model=self._effective_model(),
            )
        except Exception as error:
            self._transition_state('error', error=str(error))
            return
        if not (summary := (payload.get('text') or '').strip()):
            self._transition_state(
                'error', error=_("The provider did not return a summary."),
            )
            return
        log_entry = {
            'kind': 'command', 'name': '/compact', 'summary': summary,
            'original_messages': sum(
                1 for item in self.conversation
                if isinstance(item, dict) and item.get('role') in ('user', 'assistant')
            ),
            'original_tokens': self.last_input_tokens,
        }
        self.event_ids.sudo().unlink()
        self.write({
            'conversation': [
                {
                    'role': 'system',
                    'content': [{'type': 'input_text', 'text': self._effective_system_prompt()}]
                },
                {
                    'type': 'message',
                    'role': 'assistant',
                    'content': [{'type': 'output_text', 'text': summary}]
                },
            ],
            'pending_ask': False,
            'error_message': False,
            'last_input_tokens': 0,
            'state': 'done',
            'cleared_at': fields.Datetime.now(),
        })
        self._append_log(log_entry)
        self._publish_event('state', {'state': 'done'})
        if self.pending_ids:
            self._drain_pending_message()
            self._run_to_completion()

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
            self.sudo().write({
                'attachment_ids': [(4, aid) for aid in created.ids],
            })
        return [a._ai_describe() for a in created]

    def discard_attachments(self, attachment_ids):
        if attachment_ids:
            attachments = self.env['ir.attachment'].browse(
                [int(aid) for aid in attachment_ids],
            )
            orphans = attachments.exists().filtered(
                lambda a: (
                    a.res_model == 'muk_ai.session' and
                    a.res_id == self.id
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
        if payload is None or kind == 'none':
            self._write_view_context(None)
            return self._get_snapshot()
        self._write_view_context(clean_view_context_payload(kind, payload))
        return self._get_snapshot()

    def unpin_view_context(self):
        self._write_view_context(None)
        self._append_log({
            'kind': 'command',
            'name': '/unpin',
            'message': _("View context cleared."),
        })
        return self._get_snapshot()

    def set_approval_mode(self, mode):
        if mode and mode not in ('ask', 'off'):
            raise UserError(_("Unknown approval mode %(mode)r.", mode=mode))
        self.write({'override_approval_mode': mode or False})
        self._publish_event('state', {'state': self.state})
        return self._get_snapshot()

    def approve_tool(self):
        pending = self._require_pending_approval()
        self._record_approval_audit(
            decision='approved',
            call={'name': pending.get('name'), 'arguments': pending.get('arguments')},
            risk=pending.get('risk') or {},
        )
        self._resume_tool_round(pending, approved=True)
        if self.state == 'running':
            self._trigger_worker()
        return self._get_snapshot()

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
            call={'name': pending.get('name'), 'arguments': pending.get('arguments')},
            risk=risk,
        )
        self._resume_tool_round(pending, approved=True)
        if self.state == 'running':
            self._trigger_worker()
        return self._get_snapshot()

    def reject_tool(self, reason=None):
        pending = self._require_pending_approval()
        reason = (reason or '').strip() or _("User rejected the call.")
        self._record_approval_audit(
            decision='rejected',
            call={'name': pending.get('name'), 'arguments': pending.get('arguments')},
            risk=pending.get('risk') or {},
            reject_reason=reason,
        )
        self._resume_tool_round(pending, approved=False, reject_reason=reason)
        if self.state == 'running':
            self._trigger_worker()
        return self._get_snapshot()

    # ----------------------------------------------------------
    # Actions
    # ----------------------------------------------------------

    def action_open(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'muk_ai.chat',
            'name': self.name or _("AI Chat"),
            'params': {'session_id': self.id},
        }

    def action_stop(self):
        self.ensure_one()
        if self.state not in ('done', 'error', 'stopped'):
            self.write({'state': 'stopped', 'pending_ask': False})
            self._publish_event('state', {'state': 'stopped'})
        return self._get_snapshot()

    # ----------------------------------------------------------
    # Compute
    # ----------------------------------------------------------

    @api.depends('agent_id', 'agent_id.model_id', 'agent_id.model_id.context_window')
    def _compute_context_window(self):
        default_record = self.env['muk_ai.provider']._get_default().default_model_id
        for record in self:
            model_record = (
                record.agent_id.model_id
                if record.agent_id and record.agent_id.model_id
                else default_record
            )
            record.context_window = (
                (model_record.context_window if model_record else 0)
                or DEFAULT_CONTEXT_WINDOW
            )

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

    # ----------------------------------------------------------
    # ORM
    # ----------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        self._check_rate_limit(batch_size=len(vals_list) or 1)
        records = super().create(vals_list)
        for record in records:
            try:
                record._bus_send('muk_ai.session_state', {
                    'session_id': record.id,
                    'name': record.name,
                    'state': record.state,
                })
            except Exception:
                _logger.warning(
                    "muk_ai: failed to broadcast session create on bus",
                    exc_info=True,
                )
        return records

    # ----------------------------------------------------------
    # Cron
    # ----------------------------------------------------------

    def _capture_user_context(self):
        ctx = self.env.context or {}
        safe = {}
        for key, value in ctx.items():
            try:
                json.dumps(value)
            except (TypeError, ValueError):
                continue
            safe[key] = value
        return safe

    def _trigger_worker(self):
        if self:
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
        cron = self.env.ref(
            'muk_ai.cron_run_pending_sessions_1',
            raise_if_not_found=False,
        )
        if cron:
            cron.sudo()._trigger()

    @api.model
    def _cron_run_pending_sessions(self):
        self._sweep_orphan_sessions()
        candidates = self._find_pending_session_ids()
        if not candidates:
            return
        self._commit_safe()
        for sid in candidates:
            if self._process_session_in_worker(sid):
                break
        if len(candidates) > 1:
            self._trigger_worker()

    @api.model
    def _sweep_orphan_sessions(self):
        threshold = (
            fields.Datetime.now() - timedelta(seconds=WORKER_STALE_THRESHOLD)
        )
        orphans = self.sudo().search([
            ('state', 'in', ('running', 'compacting')),
            ('write_date', '<', threshold),
            '|',
                ('claimed_at', '=', False),
                ('claimed_at', '<', threshold),
        ])
        for session in orphans:
            try:
                with self.env.cr.savepoint():
                    session.write({
                        'state': 'error',
                        'error_message': _(
                            "Worker abandoned the session — please retry."
                        ),
                    })
                session._publish_event('state', {
                    'state': 'error', 'error': session.error_message,
                })
            except psycopg2.errors.SerializationFailure:
                continue

    @api.model
    def _find_pending_session_ids(self, limit=WORKER_CRON_COUNT):
        self.env.cr.execute(
            """
            SELECT id FROM muk_ai_session
            WHERE state IN ('running', 'compacting')
            ORDER BY write_date
            LIMIT %s
            """,
            [limit],
        )
        return [row[0] for row in self.env.cr.fetchall()]

    @api.model
    def _process_session_in_worker(self, session_id):
        with self.pool.cursor() as cr:
            cr.execute(
                "SELECT pg_try_advisory_lock(%s, %s)",
                [ADVISORY_LOCK_NAMESPACE, session_id],
            )
            if not cr.fetchone()[0]:
                return False
            try:
                env_su = api.Environment(cr, SUPERUSER_ID, {})
                session_su = env_su['muk_ai.session'].browse(session_id)
                if not session_su.exists():
                    return False
                if session_su.state not in ('running', 'compacting'):
                    return False
                owner_id = session_su.user_id.id
                saved_context = session_su.user_context or {}
                env = api.Environment(cr, owner_id, saved_context)
                session = env['muk_ai.session'].browse(session_id)
                session.write({'claimed_at': fields.Datetime.now()})
                cr.commit()
                mode = session.state
                try:
                    if mode == 'compacting':
                        session._do_compact()
                    else:
                        session._run_to_completion()
                    cr.commit()
                except StreamCancelled:
                    cr.rollback()
                except Exception as error:
                    _logger.exception(
                        "Worker failed for session %s", session_id,
                    )
                    cr.rollback()
                    self._mark_session_error(session_id, str(error))
                return True
            finally:
                try:
                    cr.execute(
                        "SELECT pg_advisory_unlock(%s, %s)",
                        [ADVISORY_LOCK_NAMESPACE, session_id],
                    )
                    cr.fetchone()
                except Exception:
                    _logger.exception(
                        "Failed to release advisory lock for session %s",
                        session_id,
                    )

    @api.model
    def _mark_session_error(self, session_id, message):
        with self.pool.cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {})
            session = env['muk_ai.session'].browse(session_id)
            if not session.exists():
                return
            session.write({
                'state': 'error',
                'error_message': message,
            })
            session._publish_event('state', {
                'state': 'error', 'error': message,
            })
            cr.commit()
