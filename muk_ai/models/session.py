import base64
import json
import re
import time

from datetime import timedelta

import requests

from odoo import _, api, fields, models, modules
from odoo.exceptions import UserError
from odoo.tools.rendering_tools import parse_inline_template, render_inline_template

from odoo.addons.muk_ai.tools import (
    ASK_USER_TOOL,
    ATTACHMENT_REF_RE,
    INLINE_IMAGE_RE,
    TERMINATING_TOOLS,
    URL_REF_RE,
    StreamCancelled,
    build_tool_call_output,
    sanitize_json_schema,
    with_ui_ctx,
)
from odoo.addons.muk_ai.tools.limits import (
    DEFAULT_CONTEXT_WINDOW,
    MAX_ITERATIONS,
    MAX_TOOL_CALLS_PER_ROUND,
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
            ('waiting', "Waiting"),
            ('stopped', "Stopped"),
            ('done', "Done"),
            ('error', "Error"),
        ],
        string="State",
        required=True,
        readonly=True,
        index=True,
        copy=False,
        default='new',
    )

    user_id = fields.Many2one(
        comodel_name='res.users',
        string="Owner",
        required=True,
        readonly=True,
        index=True,
        default=lambda self: self.env.user,
    )

    # ----------------------------------------------------------
    # Fields Configuration
    # ----------------------------------------------------------

    agent_id = fields.Many2one(
        comodel_name='muk_ai.agent',
        string="Agent",
        ondelete='set null',
        default=lambda self: self.env['muk_ai.agent']._get_default(),
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

    tool_log = fields.Json(
        string="Tool Log",
        readonly=True,
        default=list,
    )

    last_text = fields.Text(
        string="Last AI Message",
        readonly=True,
    )

    view_context = fields.Json(
        string="View Context",
        readonly=True,
        help=(
            "Sticky description of the Odoo view the user is looking at. "
            "Injected as a <ui_ctx> tag on every provider request until it "
            "is replaced by a navigation tool result or cleared via /unpin."
        ),
    )

    pending_ask = fields.Json(
        string="Pending Ask",
        readonly=True,
        help=(
            "What the session is paused on: a free-text question from "
            "ask_user (`kind: 'question'`) or a risky tool call awaiting "
            "explicit confirmation (`kind: 'approval'`). The UI reads this "
            "to render the pending ask card; the resume path depends on "
            "`kind`."
        ),
    )

    approved_signatures = fields.Json(
        string="Approved Signatures",
        readonly=True,
        help=(
            "Risk signatures the user has approved for this conversation. "
            "A signature in this list bypasses the approval gate on the "
            "next matching tool call. Scope is this session only."
        ),
    )

    pending_user_messages = fields.Json(
        string="Queued User Messages",
        readonly=True,
        help=(
            "FIFO queue of user messages typed while the session was busy. "
            "Each entry is `{content, attachment_ids, queued_at}`. Drained "
            "one-by-one at the end of `_run_to_completion`."
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
        readonly=True,
        default=0.0,
        digits=(12, 6),
        help=(
            "Cumulative USD spent on input tokens for this session. "
            "Frozen at accrual time against the model record that was "
            "active; later pricing edits do not rewrite history."
        ),
    )

    total_output_cost = fields.Float(
        string="Output Cost (USD)",
        readonly=True,
        default=0.0,
        digits=(12, 6),
        help="Cumulative USD spent on output tokens for this session.",
    )

    total_cost = fields.Float(
        string="Total Cost (USD)",
        readonly=True,
        default=0.0,
        digits=(12, 6),
        help="Cumulative USD for this session (input + output).",
    )

    last_input_tokens = fields.Integer(
        string="Last Input Tokens",
        readonly=True,
        default=0,
        help=(
            "Input tokens consumed by the most recent provider round. "
            "Drives the context-window usage meter."
        ),
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
        tools = list(self.env['muk_mcp.tool'].sudo().get_tools(
            registry='odoo'
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

    # ----------------------------------------------------------
    # Helper State
    # ----------------------------------------------------------

    def _append_log(self, entry):
        stamped = entry if 'at' in entry else {
            **entry,
            'at': fields.Datetime.now().isoformat(),
        }
        self.tool_log = [*(self.tool_log or []), stamped]
        self._publish_event('log', stamped)

    def _extend_conversation(self, items):
        self.conversation = [*(self.conversation or []), *(items or [])]

    def _resolve_attachments(self, attachment_ids):
        attachments = self.env['ir.attachment'].browse(
            [int(aid) for aid in attachment_ids or []]
        )
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

    def _recover_if_stuck(self, idle_seconds=90):
        if self.state != 'running' or not self.write_date:
            return False
        idle = (fields.Datetime.now() - self.write_date).total_seconds()
        if idle < idle_seconds:
            return False
        had_queue = bool(self.pending_user_messages)
        self.write({
            'state': 'error',
            'error_message': _(
                "Previous turn timed out after %(idle)s seconds with no "
                "activity. Session reset.",
                idle=int(idle),
            ),
            'pending_user_messages': [],
        })
        self._publish_event('state', {
            'state': 'error',
            'error': self.error_message,
        })
        if had_queue:
            self._publish_event('queue', {'pending': []})
        return True

    def _get_snapshot(self):
        return {
            'id': self.id,
            'tool_log': self.tool_log or [],
            'conversation': self.conversation or [],
            'error_message': self.error_message,
            'last_text': self.last_text,
            'attachments': [a._ai_describe() for a in self.attachment_ids],
            'total_input_cost': self.total_input_cost,
            'total_output_cost': self.total_output_cost,
            'pending_user_messages': self.pending_user_messages or [],
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
    def _check_rate_limit(self):
        if limit := self._get_rate_limit():
            count = self.sudo().search_count([
                ('user_id', '=', self.env.user.id),
                ('create_date', '>=', fields.Datetime.now() - timedelta(minutes=1)),
            ])
            if count >= limit:
                raise UserError(_(
                    "Rate limit reached (%(count)s sessions in the last minute, "
                    "max %(limit)s). Please slow down.",
                    count=count, limit=limit,
                ))

    # ----------------------------------------------------------
    # Helper Tool Dispatch
    # ----------------------------------------------------------

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
            text, _info = self.env['muk_mcp.tool']._call(
                name,
                arguments,
                self.env,
                enforce_scope=enforce_scope,
            )
        except UserError as error:
            return {'error': str(error)}, False
        except Exception as error:
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

    def _write_view_context(self, payload):
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
            self._commit_safe()
            self.invalidate_recordset(['state'])
            if self.state == 'stopped':
                raise StreamCancelled()

    def _on_stream_delta(self, kind, payload, buffer_state):
        self._check_cancelled(buffer_state)
        if kind == 'text':
            if delta :=  (payload or {}).get('delta') or '':
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
            len(buffer_state[content_key]) >= 20 or
            (now - buffer_state[last_key]) >= 0.025
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
            self._persist_partial(buffer_state)
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
                    attachment = self.env['ir.attachment'].sudo().create({
                        'name': alt or 'generated.png',
                        'datas': b64,
                        'mimetype': mimetype,
                        'res_model': self._name,
                        'res_id': self.id,
                    })
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
                        refs.append({'kind': 'attachment', 'preview_url': f'/web/image/{attachment.id}'})
                        return attachment.datas.decode()
                    return value
                if m := URL_REF_RE.match(value):
                    url = m.group(1)
                    try:
                        response = requests.get(url, timeout=30)
                        response.raise_for_status()
                        refs.append({'kind': 'url', 'preview_url': url})
                        return base64.b64encode(response.content).decode()
                    except Exception:
                        return value
                return value
            if isinstance(value, dict):
                return {k: _resolve(v) for k, v in value.items()}
            if isinstance(value, list):
                return [_resolve(v) for v in value]
            return value

        return _resolve(arguments), refs

    def _accrue_round_payload(self, payload):
        usage = payload.get('usage') or {}
        self.write({
            'iteration_count': self.iteration_count + 1,
            'total_input_tokens': self.total_input_tokens + usage.get('input_tokens', 0),
            'total_output_tokens': self.total_output_tokens + usage.get('output_tokens', 0),
            'last_input_tokens': usage.get('input_tokens', 0) or self.last_input_tokens,
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
        self._record_tool_result(
            outputs,
            call['call_id'],
            call['name'],
            {'error': reason},
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
                outputs.append(build_tool_call_output(
                    call['call_id'], {'error': 'tool_call_limit_exceeded'},
                ))
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
        while True:
            self._run_iterations(has_terminating=has_terminating)
            if self.state != 'done':
                return
            if not self._drain_pending_message():
                return
            self._transition_state('running')
            has_terminating = False

    def _run_iterations(self, has_terminating=False):
        provider, model = self._effective_provider(), self._effective_model()
        agent, tool_schema = self.agent_id, self._get_tool_schema()
        for _iteration in range(MAX_ITERATIONS):
            if self.state != 'running':
                return
            schema, round_agent = (None, None) if has_terminating else (tool_schema, agent)
            try:
                payload = self._stream_provider_round(provider, schema, model, round_agent)
            except StreamCancelled:
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

    def enqueue_message(self, user_message, attachment_ids=None):
        queue = list(self.pending_user_messages or [])
        queue.append({
            'content': user_message or '',
            'attachment_ids': list(attachment_ids or []),
            'queued_at': fields.Datetime.now().isoformat(),
        })
        self.write({'pending_user_messages': queue})
        self._publish_event('queue', {'pending': queue})
        return self._get_snapshot()

    def cancel_queued(self, index):
        queue = list(self.pending_user_messages or [])
        if 0 <= index < len(queue):
            queue.pop(index)
            self.write({'pending_user_messages': queue})
            self._publish_event('queue', {'pending': queue})
        return self._get_snapshot()

    def _drain_pending_message(self):
        queue = list(self.pending_user_messages or [])
        if not queue:
            return False
        contents = [q.get('content') or '' for q in queue]
        attachment_ids = [
            aid for q in queue for aid in (q.get('attachment_ids') or [])
        ]
        combined = '\n\n'.join(c for c in contents if c.strip())
        self.write({'pending_user_messages': []})
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
        self._record_tool_result(
            outputs,
            call['call_id'],
            call['name'],
            result
        )
        self.pending_ask = False
        self._transition_state('running')
        round_result = self._process_tool_round(
            tool_calls,
            outputs,
            resume_index + 1,
            has_terminating=has_terminating,
        )
        if round_result is not None:
            self._run_to_completion(has_terminating=round_result)

    # ----------------------------------------------------------
    # Context
    # ----------------------------------------------------------

    def _base_view_context(self, payload, kind):
        cleaned = {'kind': kind}
        if model := payload.get('model'):
            if not isinstance(model, str):
                raise UserError(_("view_context.model must be a string."))
            cleaned['model'] = model
        return cleaned

    def _view_context_domain(self, payload):
        domain = payload.get('domain')
        if domain is None:
            return None
        if not isinstance(domain, list):
            raise UserError(_("view_context.domain must be a list."))
        return domain

    def _clean_record_view_context(self, payload):
        cleaned = self._base_view_context(payload, 'record')
        res_id = payload.get('id')
        if not isinstance(res_id, int) or res_id <= 0:
            raise UserError(_("view_context.id must be a positive integer."))
        cleaned['id'] = res_id
        if display_name := payload.get('display_name'):
            if not isinstance(display_name, str):
                raise UserError(_("view_context.display_name must be a string."))
            cleaned['display_name'] = display_name
        return cleaned

    def _clean_list_view_context(self, payload):
        cleaned = self._base_view_context(payload, 'list')
        cleaned['view_type'] = payload.get('view_type') or 'list'
        if domain := self._view_context_domain(payload):
            cleaned['domain'] = domain
        return cleaned

    def _clean_action_view_context(self, payload):
        cleaned = self._base_view_context(payload, 'action')
        if action_id := payload.get('action_id'):
            if not isinstance(action_id, int):
                raise UserError(_("view_context.action_id must be an integer."))
            cleaned['action_id'] = action_id
        return cleaned

    def _clean_pivot_view_context(self, payload):
        cleaned = self._base_view_context(payload, 'pivot')
        cleaned['view_type'] = 'pivot'
        for key in ('pivot_measures', 'pivot_row_groupby', 'pivot_column_groupby'):
            value = payload.get(key)
            if value is not None:
                if not isinstance(value, list):
                    raise UserError(_("view_context.%s must be a list.", key))
                cleaned[key] = value
        if domain := self._view_context_domain(payload):
            cleaned['domain'] = domain
        return cleaned

    def _clean_graph_view_context(self, payload):
        cleaned = self._base_view_context(payload, 'graph')
        cleaned['view_type'] = 'graph'
        for key in ('graph_mode', 'graph_measure', 'graph_order'):
            value = payload.get(key)
            if value is not None:
                if not isinstance(value, str):
                    raise UserError(_("view_context.%s must be a string.", key))
                cleaned[key] = value
        groupbys = payload.get('graph_groupbys')
        if groupbys is not None:
            if not isinstance(groupbys, list):
                raise UserError(_("view_context.graph_groupbys must be a list."))
            cleaned['graph_groupbys'] = groupbys
        if domain := self._view_context_domain(payload):
            cleaned['domain'] = domain
        return cleaned

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

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
        self._run_to_completion()
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
        self._run_to_completion()
        return self._get_snapshot()

    def send_message(self, user_message, attachment_ids=None):
        self._recover_if_stuck()
        if self.state == 'running':
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
        self._run_to_completion()
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
        log = list(self.tool_log or [])
        last_user_log = None
        for idx in range(len(log) - 1, -1, -1):
            if log[idx].get('kind') == 'user_message':
                last_user_log = idx
                break
        self.tool_log = (
            log[:last_user_log + 1] if last_user_log is not None else []
        )
        self.write({
            'pending_ask': False,
            'error_message': False,
            'state': 'running',
        })
        self._publish_event('state', {'state': 'running'})
        self._run_to_completion()
        return self._get_snapshot()

    def clear(self):
        if self.state == 'running':
            raise UserError(_(
                "Cannot clear the conversation while the session is running.",
            ))
        log_entry = {
            'kind': 'command',
            'name': '/clear',
            'message': _("Conversation cleared."),
        }
        self.write({
            'conversation': [],
            'tool_log': [log_entry],
            'pending_ask': False,
            'approved_signatures': [],
            'last_text': False,
            'error_message': False,
            'iteration_count': 0,
            'last_input_tokens': 0,
            'state': 'new',
            'pending_user_messages': [],
        })
        self._publish_event('log', log_entry)
        self._publish_event('state', {'state': 'new'})
        self._publish_event('queue', {'pending': []})
        return self._get_snapshot()

    def compact(self):
        if self.state == 'running':
            raise UserError(_("Cannot compact while the session is running. Stop first."))
        if self.state == 'waiting':
            raise UserError(_("Cannot compact while the session is waiting for user input."))
        if not self.conversation:
            raise UserError(_("Nothing to compact yet — the conversation is empty."))
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
            raise UserError(_("Failed to compact conversation: %s", error)) from error
        if not (summary := (payload.get('text') or '').strip()):
            raise UserError(_("The provider did not return a summary."))
        log_entry = {
            'kind': 'command', 'name': '/compact', 'summary': summary,
            'original_messages': sum(
                1 for item in self.conversation
                if isinstance(item, dict) and item.get('role') in ('user', 'assistant')
            ),
            'original_tokens': self.last_input_tokens,
        }
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
        })
        self._append_log(log_entry)
        self._publish_event('state', {'state': self.state})
        return self._get_snapshot()

    def upload_attachments(self, files):
        created = self.env['ir.attachment']
        for entry in files or []:
            created |= created._ai_create_from_upload(
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
        cleaner = (
            getattr(self, f'_clean_{kind}_view_context', None)
            if isinstance(kind, str)
            and kind.isidentifier()
            and not kind.startswith('_')
            else None
        )
        if not cleaner:
            raise UserError(_(
                "Invalid view context payload (kind=%(kind)r).",
                kind=kind,
            ))
        self._write_view_context(cleaner(payload))
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
        self.override_approval_mode = mode or False
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
        for record in self:
            record.context_window = record._resolve_context_window()

    @api.depends('override_approval_mode', 'agent_id', 'agent_id.approval_mode')
    def _compute_effective_approval_mode(self):
        for record in self:
            record.effective_approval_mode = record._effective_approval_mode()

    # ----------------------------------------------------------
    # ORM
    # ----------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        self._check_rate_limit()
        return super().create(vals_list)
