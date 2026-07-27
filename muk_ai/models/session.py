from __future__ import annotations

import base64
import json
import random
import re
import threading
import time
from collections.abc import Container, Iterable
from contextlib import suppress
from datetime import timedelta

import psycopg2
import urllib3
from markupsafe import Markup, escape

from odoo import SUPERUSER_ID, _, api, fields, models, modules, release
from odoo.exceptions import AccessError, UserError
from odoo.http import request
from odoo.tools import SQL, config

from odoo.addons.muk_ai.tools import (
    ADVISORY_LOCK_NAMESPACE,
    ALLOWED_MIMETYPES,
    ASK_USER_TOOL,
    ATTACHMENT_REF_MAX_BYTES,
    ATTACHMENT_REF_RE,
    CLIENT_ACTION_TIMEOUT_SECONDS,
    COMPACT_AUTO_RATIO,
    COMPACT_SUMMARY_REINJECTION,
    COMPACT_SUMMARY_SYSTEM,
    COMPACT_SUMMARY_TEMPLATE,
    DEFAULT_CONTEXT_WINDOW,
    DISPATCH_MAX_TURNS,
    IMAGE_MIMETYPES,
    INLINE_IMAGE_RE,
    ITERATION_WARNING_ROUNDS,
    MAX_ITERATIONS,
    MAX_TOOL_CALLS_PER_ROUND,
    MAX_WALLCLOCK_SECONDS,
    TERMINATING_TOOLS,
    TOOL_LOAD_TOOL,
    TOOL_VISION_MAX_B64_CHARS,
    TOOL_VISION_MAX_IMAGES,
    TURN_WALLCLOCK_SECONDS,
    URL_REF_RE,
    WALLCLOCK_MIN_SECONDS,
    WALLCLOCK_SAFETY_MARGIN,
    WORKER_HEARTBEAT_INTERVAL,
    WORKER_STALE_THRESHOLD,
    StreamCancelled,
    build_tool_call_output,
    clean_ask_preview,
    clean_view_context_payload,
    extract_sources,
    fetch_url,
    format_tool_signature,
    is_unmaterialized_attachment,
    sanitize_json_schema,
    summarize_tool_description,
    tool_file_payload,
    with_ui_ctx,
)

PG_CONCURRENCY_EXCEPTIONS_TO_RETRY = (
    psycopg2.errors.LockNotAvailable,
    psycopg2.errors.SerializationFailure,
    psycopg2.errors.DeadlockDetected,
)


def has_access(records: models.BaseModel, operation: str) -> bool:
    """Return whether the current user may perform ``operation`` on ``records``.

    Replaces the ``has_access`` model method, which only exists from 18.0 on.
    """
    try:
        records.check_access_rights(operation)
        records.check_access_rule(operation)
    except AccessError:
        return False
    return True


class AISession(models.Model):
    """Stateful agent conversation: runtime, streaming, tools, and approvals."""

    _name = 'muk_ai.session'
    _description = 'AI Session'
    _order = 'create_date desc'

    # ----------------------------------------------------------
    # Fields Identity
    # ----------------------------------------------------------

    name = fields.Char(
        string='Name',
        required=True,
        index=True,
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

    claimed_at = fields.Datetime(
        string='Worker Claimed At',
        help=(
            'Heartbeat written by the cron worker while processing this '
            'session. Sessions in `running` or `compacting` state with a '
            'stale heartbeat are reclaimed as orphans by the next cron tick.'
        ),
        readonly=True,
        index=True,
        copy=False,
    )

    user_context = fields.Json(
        string='User Context',
        help=(
            "Snapshot of the calling user's environment context captured at "
            'trigger time. Restored by the cron worker so tools see the same '
            'language, timezone, and allowed companies as the originating '
            'request.'
        ),
        readonly=True,
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

    # ----------------------------------------------------------
    # Fields Configuration
    # ----------------------------------------------------------

    agent_id = fields.Many2one(
        comodel_name='muk_ai.agent',
        string='Agent',
        default=lambda self: self.env['muk_ai.agent']._get_default(),
        ondelete='set null',
    )

    override_approval_mode = fields.Selection(
        selection=[
            ('ask', 'Ask on writes'),
            ('off', 'Never ask'),
        ],
        string='Approval Mode Override',
        help=(
            "Per-session override for the agent's approval policy. "
            'Leave empty to inherit from the agent.'
        ),
    )

    effective_approval_mode = fields.Char(
        compute='_compute_effective_approval_mode',
        string='Effective Approval Mode',
    )

    # ----------------------------------------------------------
    # Fields State
    # ----------------------------------------------------------

    conversation = fields.Json(
        string='Conversation',
        readonly=True,
        default=list,
    )

    cleared_at = fields.Datetime(
        string='Cleared At',
        help='Wall-clock marker set by /clear and /compact.',
        readonly=True,
        copy=False,
    )

    notification_unread = fields.Boolean(
        string='Notification Unread',
        help=(
            'Set on a terminal state change, cleared when the user opens '
            'the session; drives the systray attention badge.'
        ),
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
        help=(
            'Flat list of session events in the shape consumed by the '
            "chat-style events widget. Mirrors `fetch_events()['events']`."
        ),
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
    )

    view_context = fields.Json(
        string='View Context',
        help=(
            'Sticky description of the Odoo view the user is looking at. '
            'Injected as a <ui_ctx> tag on every provider request until it '
            'is replaced by a navigation tool result or cleared via /unpin.'
        ),
        readonly=True,
    )

    deferred_vision_attachment_ids = fields.Json(
        string='Deferred Vision Attachments',
        help=(
            'Attachment ids of images returned by tools in the current round, '
            'held until every function_call_output of the round is emitted so '
            'the images follow all tool results (required by vision providers).'
        ),
        readonly=True,
    )

    pending_ask = fields.Json(
        string='Pending Ask',
        help=(
            'What the session is paused on: a free-text question from '
            "ask_user (`kind: 'question'`) or a risky tool call awaiting "
            "explicit confirmation (`kind: 'approval'`). The UI reads this "
            'to render the pending ask card; the resume path depends on '
            '`kind`.'
        ),
        readonly=True,
    )

    approved_signatures = fields.Json(
        string='Approved Signatures',
        help=(
            'Risk signatures the user has approved for this conversation. '
            'A signature in this list bypasses the approval gate on the '
            'next matching tool call. Scope is this session only.'
        ),
        readonly=True,
    )

    pending_ids = fields.One2many(
        comodel_name='muk_ai.session.pending',
        string='Pending Messages',
        help=(
            'FIFO queue of user messages typed while the session was busy. '
            'Drained as one combined turn at the end of `_run_to_completion`.'
        ),
        readonly=True,
        inverse_name='session_id',
    )

    expanded_tool_names = fields.Json(
        string='Loaded Tools',
        help=(
            'Tool names whose full schemas have been loaded into this '
            'session via tool_load. Append-only within a session. '
            'Essentials and meta-tools (tool_load, ask_user) are always '
            'loaded regardless of this list.'
        ),
        readonly=True,
        default=list,
    )

    pending_user_messages = fields.Json(
        compute='_compute_pending_user_messages',
        string='Queued User Messages',
        help=(
            'Serialized snapshot of `pending_ids` in the shape consumed by '
            'the chat client.'
        ),
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

    # ----------------------------------------------------------
    # Fields Usage
    # ----------------------------------------------------------

    iteration_count = fields.Integer(
        string='Iterations',
        readonly=True,
        default=0,
    )

    turn_wallclock_spent = fields.Float(
        string='Turn Wallclock Spent',
        help=(
            'Cumulative compute seconds spent on the current user turn across '
            'cron slices. Reset to zero on each new user turn. When it reaches '
            'the per-turn wallclock budget the turn stops with an error.'
        ),
        readonly=True,
        default=0.0,
        copy=False,
    )

    turn_cost_spent = fields.Float(
        string='Turn Cost Spent',
        help=(
            'Cumulative amount spent on the current user turn across cron '
            'slices, in the price currency of the model. Reset to zero on '
            'each new user turn. When it reaches the per-turn cost limit '
            '(muk_ai.turn_cost_limit) the turn stops with an error.'
        ),
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
        help=(
            'Cumulative USD spent on input tokens for this session. '
            'Frozen at accrual time against the model record that was '
            'active; later pricing edits do not rewrite history.'
        ),
        readonly=True,
        default=0.0,
        digits=(12, 6),
    )

    total_output_cost = fields.Float(
        string='Output Cost (USD)',
        help='Cumulative USD spent on output tokens for this session.',
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
        help=(
            'Input tokens consumed by the most recent provider round. '
            'Drives the context-window usage meter.'
        ),
        readonly=True,
        default=0,
    )

    context_window = fields.Integer(
        compute='_compute_context_window',
        string='Context Window',
        help="Effective context window size for the session's active model.",
    )

    # ----------------------------------------------------------
    # Helper Resolvers
    # ----------------------------------------------------------

    @api.model
    def _get_terminating_tools(self) -> set[str]:
        """Return the names of tools that terminate a tool round."""
        return TERMINATING_TOOLS

    @api.model
    def _get_system_prompt(self) -> str:
        """Return the default agent's system prompt."""
        return self.env['muk_ai.agent']._get_default().system_prompt

    def _effective_system_prompt(self) -> str:
        """Render the session's system prompt from its agent or the default."""
        raw = (
            self.agent_id.system_prompt
            if self.agent_id and self.agent_id.system_prompt
            else self._get_system_prompt()
        )
        return self._render_system_prompt(raw or '')

    def _system_prompt_addenda(self) -> list[str]:
        """Return capability blocks appended after the agent system prompt.

        Extension modules override this to contribute focused-element, skill,
        todo, browser or workflow guidance without polluting the agent's own
        rendered prompt in :meth:`_effective_system_prompt`, mirroring how the
        runtime and available-tools blocks are assembled as separate parts.
        """
        return []

    def _build_available_tools_block(self) -> str:
        """Build the prompt block summarizing the deferred tools."""
        catalog = {
            entry['name']: (
                format_tool_signature(entry['name'], entry.get('inputSchema')),
                summarize_tool_description(entry.get('description')),
            )
            for entry in self._get_filtered_catalog()
            if entry.get('name')
        }
        loaded = set(self._loaded_tool_names()) & set(catalog)
        if deferred := sorted(set(catalog) - loaded):
            lines = [
                '<available_tools>',
                (
                    'This list is COMPLETE: every tool the session can call '
                    'is either in your `tools` array (immediately callable) '
                    'or listed below. Do NOT call list_models or any '
                    'other tool to look for tools — every name is here.'
                ),
                (
                    'To use a tool listed below, call tool_load with a '
                    '`call` argument that loads the schema AND executes the '
                    'tool in ONE round-trip:'
                ),
                'tool_load(names=["<tool>"], call={name: "<tool>", arguments: {...}})',
                (
                    'Returns {loaded: {...}, call: {output: <result>}}. No '  # noqa: RUF027 — literal prompt text, not an f-string
                    'follow-up turn. This is the strongly preferred shape '
                    'for any deferred tool — never load and then call in '
                    'two separate rounds when one will do.'
                ),
                (
                    'Each line below is `name(arguments): summary`, where `*` '
                    'marks a required argument. Pass ONLY the arguments listed '
                    'for that tool — anything else is rejected. The summary is '
                    'abbreviated; tool_load returns the full schema.'
                ),
                *self._available_tools_extra_paragraphs(),
                *(
                    f'{signature}: {summary}' if summary else signature
                    for name in deferred
                    for signature, summary in (catalog[name],)
                ),
                '</available_tools>',
            ]
            return '\n'.join(lines)
        return ''

    def _build_files_block(self) -> str:
        """Build the prompt block stating how to hand a file to the user."""
        return (
            '<files>\n'
            'NEVER write file contents yourself: no `data:` URIs, no '
            'hand-written base64. Base64 you compose is always corrupt, and '
            'the chat strips `data:` links, so the user gets a dead link and '
            'a broken file.\n'
            'To give the user a file, call the tool that produces it (see '
            '<available_tools> for the exporting and reporting tools). Such a '
            'tool returns a `url`; link that URL directly, e.g. '
            '[Download](/web/content/42?download=1). Always include that link: '
            'it is how the user opens the file, and the file also appears in '
            'the Attachments panel of the chat.\n'
            'To read a stored file back yourself, pass its `attachment_id` to '
            'read_resource as `odoo://attachment/<id>`.\n'
            '</files>'
        )

    def _available_tools_extra_paragraphs(self) -> list[str]:
        """Return extra paragraphs appended to the available-tools block."""
        return []

    def _session_prompt_extras(self) -> dict:
        """Return template variables exposed to the system prompt."""
        return {
            'approval_mode': (
                self._effective_approval_mode() if self and self.id else 'ask'
            ),
        }

    def _render_system_prompt(self, raw: str) -> str:
        """Render a raw system prompt with the session's template extras."""
        agent = self.agent_id or self.env['muk_ai.agent']._get_default()
        return agent._render_prompt(raw, **self._session_prompt_extras())

    def _build_runtime_block(self) -> str:
        """Build the prompt block stating runtime facts about the session."""
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

    def _effective_model_record(self) -> models.BaseModel:
        """Return the model record used by the session's agent or default."""
        if self.agent_id and self.agent_id.model_id:
            return self.agent_id.model_id
        return self.env['muk_ai.provider']._get_default().default_model_id

    def _effective_provider(self) -> models.BaseModel:
        """Return the provider backing the session's effective model."""
        if record := self._effective_model_record():
            return record.provider_id
        return self.env['muk_ai.provider']._get_default()

    def _effective_model(self) -> str | None:
        """Return the technical name of the effective model, or ``None``."""
        if record := self._effective_model_record():
            return record.technical_name
        return None

    def _resolve_context_window(self) -> int:
        """Return the effective model's context window, or the default."""
        record = self._effective_model_record()
        return (record.context_window if record else 0) or DEFAULT_CONTEXT_WINDOW

    def _effective_approval_mode(self) -> str:
        """Return the approval mode from the override, agent, or default."""
        if self.override_approval_mode:
            return self.override_approval_mode
        if self.agent_id and self.agent_id.approval_mode:
            return self.agent_id.approval_mode
        return 'ask'

    @api.model
    def _int_config_param(self, key: str, default: int) -> int:
        """Return a positive integer config parameter, or the default."""
        raw = self.env['ir.config_parameter'].sudo().get_param(key)
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return default
        return value if value > 0 else default

    @api.model
    def _max_iterations(self) -> int:
        """Return the configured maximum LLM rounds per worker slice."""
        return self._int_config_param('muk_ai.max_iterations', MAX_ITERATIONS)

    @api.model
    def _worker_hard_limit_seconds(self) -> int:
        """Return the real-time budget of the current worker context.

        :return: seconds left in a request thread, the configured cron limit
            outside one, or ``0`` when no limit applies
        """
        thread = threading.current_thread()
        if getattr(thread, 'type', None) == 'http':
            limit = config['limit_time_real'] or 0
            if limit <= 0:
                return 0
            started = getattr(thread, 'start_time', None) or time.time()
            return max(1, int(limit - (time.time() - started)))
        limit = config['limit_time_real_cron']
        if not limit or limit < 0:
            limit = config['limit_time_real'] or 0
        return limit if limit and limit > 0 else 0

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
        raw = self.env['ir.config_parameter'].sudo().get_param('muk_ai.turn_cost_limit')
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return 0.0
        return value if value > 0 else 0.0

    # ----------------------------------------------------------
    # Helper Inputs
    # ----------------------------------------------------------

    @staticmethod
    def _tool_entry_to_schema(entry: dict) -> dict:
        """Convert a tool catalog entry into a provider function schema."""
        schema = entry.get('inputSchema') or {'type': 'object', 'properties': {}}
        return {
            'type': 'function',
            'name': entry['name'],
            'description': entry.get('description') or '',
            'parameters': sanitize_json_schema(schema),
            'strict': False,
        }

    def _build_user_entry(
        self,
        user_message: str | None = None,
        attachments: models.BaseModel | None = None,
    ) -> dict | None:
        """Build a user conversation entry from a message and attachments."""
        content = []
        if user_message:
            content.append({'type': 'input_text', 'text': user_message})
        for attachment in attachments or []:
            content.append(
                {
                    'type': 'muk_ai_attachment',
                    'attachment_id': attachment.id,
                    'filename': attachment.name,
                    'mimetype': attachment.mimetype,
                }
            )
        return {'role': 'user', 'content': content} if content else None

    def _system_message(self) -> dict:
        """Return the system message rebuilt from the current agent and context."""
        parts = [
            self._effective_system_prompt(),
            *self._system_prompt_addenda(),
            self._build_runtime_block(),
            self._build_files_block(),
            self._build_available_tools_block(),
        ]
        return {
            'role': 'system',
            'content': [
                {
                    'type': 'input_text',
                    'text': '\n\n'.join(part for part in parts if part),
                }
            ],
        }

    def _build_initial_inputs(
        self,
        user_message: str | None = None,
        attachments: models.BaseModel | None = None,
    ) -> list[dict]:
        """Build the initial user input for a fresh turn (system prompt added per request)."""
        if user_entry := self._build_user_entry(user_message, attachments):
            return [user_entry]
        return []

    def _user_message_log(
        self, user_message: str | None, attachments: models.BaseModel
    ) -> dict:
        """Build the persisted log entry for a user message."""
        return {
            'kind': 'user_message',
            'content': user_message or '',
            'attachments': [a._ai_describe() for a in attachments],
        }

    def _available_client_kinds(self) -> set[str]:
        """Return the client kinds whose executor can currently answer.

        Overridable hook: every module contributing ``execute == 'client'``
        tools adds its kind while the matching executor is reachable. Core
        ships the ``webclient`` kind, answered by the chat client running
        in the user's browser tab.
        """
        return {'webclient'}

    def _get_filtered_catalog(self) -> list[dict]:
        """Return the tool catalog filtered by agent and client availability.

        Client-executed tools (``_meta.execute == 'client'``) are dropped
        unless their declared ``_meta.client`` kind is currently available
        (see ``_available_client_kinds``).
        """
        tool_env = self.env(
            context={**self.env.context, **self._tool_dispatch_context()}
        )
        catalog = list(tool_env['muk_mcp.tool'].sudo().get_tools(registry='odoo'))
        if self.agent_id:
            catalog = self.agent_id.apply_tool_filter(catalog)
        kinds = self._available_client_kinds()
        return [
            entry
            for entry in catalog
            if (meta := entry.get('_meta') or {}).get('execute') != 'client'
            or meta.get('client') in kinds
        ]

    def _tool_client_kind(self, name: str) -> str | None:
        """Return the declared client kind of a registered tool, or ``None``.

        Reads the raw registry: the kind is a static registration property,
        so routing decisions (e.g. mirroring an approved browser action to
        the extension) must not depend on the tool's current visibility —
        the agent filter can change between a gate pause and its resume.
        """
        for entry in self.env['muk_mcp.tool'].sudo().get_tools(registry='odoo'):
            if entry.get('name') == name:
                meta = entry.get('_meta') or {}
                if meta.get('execute') == 'client':
                    return meta.get('client')
                return None
        return None

    def _get_essential_tool_names(self) -> list[str]:
        """Return the essential tool names plus every visible client tool.

        Client tools load their full schemas upfront so a call pauses on the
        client-action seam instead of being loaded and inline-called through
        ``tool_load`` (which would execute it without pausing for the client).
        """
        if self.agent_id:
            names = list(self.agent_id._get_essential_tool_names())
        else:
            names = list(self.env['muk_ai.agent']._get_default_essential_tool_names())
        names.extend(
            entry['name']
            for entry in self._get_filtered_catalog()
            if entry.get('name')
            and entry['name'] not in names
            and (entry.get('_meta') or {}).get('execute') == 'client'
        )
        return names

    def _loaded_tool_names(self) -> list[str]:
        """Return the de-duplicated essential and expanded tool names."""
        seen, result = set(), []
        for name in self._get_essential_tool_names() + list(
            self.expanded_tool_names or []
        ):
            if name and name not in seen:
                seen.add(name)
                result.append(name)
        return result

    def _get_tool_schema(self) -> list[dict]:
        """Build the function schema list for currently loaded tools."""
        catalog_by_name = {
            entry['name']: entry for entry in self._get_filtered_catalog()
        }
        loaded = set(self._loaded_tool_names()) & set(catalog_by_name)
        result = [
            self._tool_entry_to_schema(catalog_by_name[name]) for name in sorted(loaded)
        ]
        if set(catalog_by_name) - loaded:
            result.append(self._tool_entry_to_schema(TOOL_LOAD_TOOL))
        if self._effective_approval_mode() != 'off' and 'ask_user' not in loaded:
            result.append(self._tool_entry_to_schema(ASK_USER_TOOL))
        return result

    @staticmethod
    def _strip_internal_keys(items: Iterable) -> list:
        """Return conversation items without internal underscore-prefixed keys."""
        return [
            {key: value for key, value in item.items() if not key.startswith('_')}
            if isinstance(item, dict)
            else item
            for item in (items or [])
        ]

    def _build_request_inputs(self) -> list[dict]:
        """Return a fresh system message followed by the annotated conversation.

        Any system item persisted by an older version is dropped so the system
        message always reflects the current agent.
        """
        self._close_orphan_tool_calls('tool result missing')
        history = [
            item
            for item in self._strip_internal_keys(self.conversation)
            if not (isinstance(item, dict) and item.get('role') == 'system')
        ]
        return [
            self._system_message(),
            *with_ui_ctx(history, self.view_context),
        ]

    # ----------------------------------------------------------
    # Helper Bus
    # ----------------------------------------------------------

    def _bus_channel(self) -> models.BaseModel:
        """Return the partner used as the session's bus channel."""
        return self.user_id.partner_id

    def _bus_send(self, notification_type: str, message: dict) -> None:
        """Send a notification to the webclient on each record's channel.

        Replaces ``bus.listener.mixin``, which only exists from 18.0 on.
        """
        for record in self:
            channel = record._bus_channel()
            channel.ensure_one()
            self.env['bus.bus']._sendone(channel, notification_type, message)

    def _public_pending_ask(self, pending: dict | None = None) -> dict | None:
        """Return the pending ask payload stripped of internal keys."""
        pending = self.pending_ask if pending is None else pending
        if not isinstance(pending, dict) or not pending:
            return None
        public = {
            key: value
            for key, value in pending.items()
            if key
            not in (
                'arguments',
                'tool_calls',
                'outputs',
                'resume_index',
                'has_terminating',
                'results',
            )
        }
        if isinstance(public.get('actions'), list):
            results = pending.get('results') or {}
            public['actions'] = [
                {
                    'call_id': action.get('call_id'),
                    'name': action.get('name'),
                    'done': action.get('call_id') in results,
                }
                for action in public['actions']
            ]
        return public

    def _state_metrics(self) -> dict:
        """Return the public state and usage metrics broadcast on the bus."""
        return {
            'state': self.state,
            'iteration_count': self.iteration_count,
            'total_input_tokens': self.total_input_tokens,
            'total_output_tokens': self.total_output_tokens,
            'last_input_tokens': self.last_input_tokens,
            'context_window': self._resolve_context_window(),
            'view_context': self.view_context or None,
            'pending_ask': self._public_pending_ask(),
            'override_approval_mode': self.override_approval_mode or False,
            'effective_approval_mode': self._effective_approval_mode(),
            'total_cost': self.total_cost,
        }

    def _publish_event(self, event_type: str, payload: dict) -> None:
        """Broadcast a session event and any derived state notifications."""
        self._bus_send(
            'muk_ai.event',
            {
                'session_id': self.id,
                'type': event_type,
                'payload': payload,
            },
        )
        if event_type == 'state':
            self._bus_send(
                'muk_ai.session_state',
                {
                    'session_id': self.id,
                    'name': self.name,
                    **self._state_metrics(),
                },
            )
            self._notify_state_transition(payload)
        elif event_type == 'rename':
            self._bus_send(
                'muk_ai.session_state',
                {
                    'session_id': self.id,
                    'name': self.name,
                    'state': self.state,
                },
            )

    def _bus_log_payload(self, payload: dict, limit: int = 8192) -> dict:
        """Return a copy of the payload with large fields truncated for the bus."""
        capped = dict(payload)
        for key in ('result', 'arguments'):
            if (value := capped.get(key)) is None:
                continue
            text = value if isinstance(value, str) else json.dumps(value, default=str)
            if len(text) > limit:
                capped[key] = text[:limit] + '…'
                capped['truncated'] = True
        return capped

    def _notify_state_transition(self, payload: dict) -> None:
        """Emit bus and inbox notifications for terminal state transitions."""
        new_state = (payload or {}).get('state')
        if new_state == 'done' and (
            self.pending_ids or self.env.context.get('muk_ai_skip_done_notification')
        ):
            return
        if new_state in ('done', 'waiting', 'error'):
            ask = (payload or {}).get('ask') or self.pending_ask or {}
            ask_kind = ask.get('kind') if isinstance(ask, dict) else None
            title, message = self._notification_summary(new_state, payload, ask_kind)
            self.notification_unread = True
            with suppress(Exception):
                self._bus_send(
                    'muk_ai.session_notification',
                    {
                        'session_id': self.id,
                        'session_name': self.name,
                        'state': new_state,
                        'ask_kind': ask_kind,
                        'title': title,
                        'message': message,
                        'at': fields.Datetime.to_string(fields.Datetime.now()),
                    },
                )
            self._post_inbox_notification(title, message)
            self._push_notification_badge(self.user_id)

    def _notification_summary(
        self, new_state: str, payload: dict, ask_kind: str | None
    ) -> tuple[str, str]:
        """Return the notification title and message for a state transition."""
        name = self.name or _('AI Session')
        if new_state == 'done':
            return (
                _('AI session finished'),
                _('Session “%(name)s” has finished.', name=name),
            )
        if new_state == 'error':
            raw = (payload or {}).get('error') or self.error_message
            return (
                _('AI session error'),
                _(
                    'Session “%(name)s” stopped: %(reason)s',
                    name=name,
                    reason=self._short_error_reason(raw) if raw else _('unknown error'),
                ),
            )
        if ask_kind == 'approval':
            return (
                _('AI session needs approval'),
                _(
                    'Session “%(name)s” is waiting for your approval before '
                    'running a tool.',
                    name=name,
                ),
            )
        return (
            _('AI session needs your input'),
            _('Session “%(name)s” is waiting for your answer.', name=name),
        )

    def _short_error_reason(self, raw: str) -> str:
        """Extract a short, single-line reason from a raw error string."""
        text = raw.strip()[:8192]
        if match := re.search(r'\{.*\}', text, flags=re.DOTALL):
            try:
                data = json.loads(match.group(0))
            except ValueError:
                data = None
            if isinstance(data, dict):
                error = data.get('error')
                if isinstance(error, dict) and error.get('message'):
                    text = error['message']
                elif data.get('message'):
                    text = data['message']
        text = ' '.join(text.split())
        return text[:197] + '…' if len(text) > 200 else text

    def _post_inbox_notification(self, title: str, message: str) -> None:
        """Notify the owner through Discuss inbox and mobile/web push.

        Routes through ``message_notify`` so the standard pipeline fires web
        push and Enterprise OCN mobile push. Only inbox-preference owners are
        notified; email-preference owners would receive an email per event, so
        they are skipped and rely on the systray badge instead.

        ``notify_author`` is required because the session runs in its owner's
        environment, and recipients matching the acting user are dropped from
        the recipient list by default.
        """
        user = self.user_id
        if not user or not user.partner_id or user.notification_type != 'inbox':
            return
        with suppress(Exception):
            mail_message = self.env['mail.thread'].message_notify(
                partner_ids=user.partner_id.ids,
                model=self._name,
                res_id=self.id,
                author_id=self.env.ref('base.partner_root').id,
                subject=title,
                body=Markup('<p>%s</p>') % escape(message),
                notify_author=True,
            )
            if mail_message:
                mail_message.sudo().muk_ai_session_id = self.id

    # ----------------------------------------------------------
    # Helper State
    # ----------------------------------------------------------

    def _append_event(self, entry: dict) -> models.BaseModel:
        """Append an event with the next sequence and broadcast it."""
        stamped = (
            entry
            if 'at' in entry
            else {**entry, 'at': fields.Datetime.now().isoformat()}
        )
        event = self.env['muk_ai.session.event'].sudo()
        for _attempt in range(5):
            self.env.cr.execute(
                SQL(
                    'SELECT COALESCE(MAX(sequence), -1) + 1 '
                    'FROM muk_ai_session_event WHERE session_id = %s',
                    self.id,
                )
            )
            sequence = self.env.cr.fetchone()[0]
            try:
                with self.env.cr.savepoint():
                    event = (
                        self.env['muk_ai.session.event']
                        .sudo()
                        .create(
                            {
                                'session_id': self.id,
                                'sequence': sequence,
                                'kind': stamped.get('kind') or '',
                                'payload': stamped,
                                'at': fields.Datetime.now(),
                            }
                        )
                    )
                stamped = {**stamped, 'event_id': event.id}
                break
            except psycopg2.errors.UniqueViolation:
                continue
        self._publish_event('log', self._bus_log_payload(stamped))
        return event

    def _extend_conversation(self, items: list[dict]) -> None:
        """Append items to the stored conversation."""
        self.conversation = [*(self.conversation or []), *(items or [])]

    def _close_orphan_tool_calls(self, reason: str) -> None:
        """Emit interrupted outputs for tool calls left without a result."""
        conversation = self.conversation or []
        answered = {
            item.get('call_id')
            for item in conversation
            if isinstance(item, dict) and item.get('type') == 'function_call_output'
        }
        orphans = [
            item['call_id']
            for item in conversation
            if isinstance(item, dict)
            and item.get('type') == 'function_call'
            and item.get('call_id')
            and item['call_id'] not in answered
        ]
        if orphans:
            self._extend_conversation(
                [
                    build_tool_call_output(
                        call_id,
                        {
                            'error': 'interrupted',
                            'reason': reason,
                        },
                    )
                    for call_id in orphans
                ]
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
        if (attachments := requested.exists()) != requested:
            raise UserError(_('One or more attachments could not be found.'))
        attachments._ai_validate()
        if new := attachments - self.attachment_ids:
            if new.filtered(lambda a: a.res_model and a.res_model != 'muk_ai.session'):
                raise UserError(_('One or more attachments could not be found.'))
            new.check_access_rights('write')
            new.check_access_rule('write')
            new.sudo().write({'res_model': 'muk_ai.session', 'res_id': self.id})
            self.invalidate_recordset(['attachment_ids'])
        return attachments

    def _enqueue_user_turn(
        self,
        user_message: str | None,
        attachments: models.BaseModel,
        extend: bool = True,
    ) -> None:
        """Start a running turn from a user message and attachments."""
        if extend and (user_entry := self._build_user_entry(user_message, attachments)):
            self._extend_conversation([user_entry])
        if user_message or attachments:
            self._append_event(self._user_message_log(user_message, attachments))
        self.write(
            {
                'state': 'running',
                'error_message': False,
                'claimed_at': False,
                'turn_wallclock_spent': 0.0,
                'turn_cost_spent': 0.0,
            }
        )
        self._publish_event('state', {'state': 'running'})

    def _record_tool_result(
        self,
        outputs: list,
        call_id: str,
        name: str,
        output_result,
        log_result=None,
        arguments: dict | None = None,
    ) -> None:
        """Append a tool output and record the matching result event.

        Image-bearing results are split: the text-only payload becomes the
        ``function_call_output`` and any images are persisted and appended as a
        follow-up user entry so the vision model can see them. Any citable
        sources the call surfaced (a fetched page, a read record) are attached
        to the event so the client can render them in the sources rail.
        """
        cleaned = self._append_tool_output_with_vision(outputs, call_id, output_result)
        event = {
            'kind': 'tool_result',
            'name': name,
            'result': cleaned if log_result is None else log_result,
            'call_id': call_id,
        }
        if sources := extract_sources(name, arguments, output_result):
            event['sources'] = sources
        self._append_event(event)

    def _persist_synthetic_event(self, call: dict, result, status: str) -> None:
        """Persist an MCP log entry for a synthetic (non-provider) tool call."""
        arguments = call.get('arguments') or {}
        self.env['muk_mcp.log'].sudo().create(
            {
                'method': 'tools/call',
                'tool_name': call.get('name') or '',
                'model_name': (
                    arguments.get('model') or '' if isinstance(arguments, dict) else ''
                ),
                'user_id': self.env.uid,
                'status': status,
                'duration_ms': 0,
                'request_data': json.dumps(arguments, default=str),
                'response_data': json.dumps(result, default=str),
                'error_message': (
                    result.get('error') or result.get('reason')
                    if isinstance(result, dict)
                    else None
                ),
                'source': 'chat',
                'session_id': self.id,
            }
        )

    def _commit_safe(self) -> None:
        """Commit outside tests, re-raising on serialization conflicts."""
        if not modules.module.current_test:
            try:
                self.env.cr.commit()
            except PG_CONCURRENCY_EXCEPTIONS_TO_RETRY:
                self.env.cr.rollback()
                self.invalidate_recordset()
                raise

    def _transition_state(self, state: str, error: str | None = None) -> None:
        """Persist a new state and publish the matching state event."""
        self.write({'state': state} | ({'error_message': error} if error else {}))
        self._publish_event(
            'state', {'state': state} | ({'error': error} if error else {})
        )

    def _recover_if_stuck(self, idle_seconds: int = WORKER_STALE_THRESHOLD) -> bool:
        """Mark a stalled running session as errored when idle too long."""
        if self.state in ('running', 'compacting') and (
            reference := self.claimed_at or self.write_date
        ):
            idle = (fields.Datetime.now() - reference).total_seconds()
            if idle >= idle_seconds and self._try_session_xact_lock(self.id):
                self._close_orphan_tool_calls('previous turn timed out')
                self.write(
                    {
                        'state': 'error',
                        'error_message': _(
                            'Previous turn timed out after %(idle)s seconds with no activity.',
                            idle=int(idle),
                        ),
                    }
                )
                self._publish_event(
                    'state', {'state': 'error', 'error': self.error_message}
                )
                return True
        return False

    @api.model
    def _try_session_xact_lock(self, session_id: int) -> bool:
        """Try to take a transaction-scoped advisory lock on the session."""
        self.env.cr.execute(
            SQL(
                'SELECT pg_try_advisory_xact_lock(%s, %s)',
                ADVISORY_LOCK_NAMESPACE,
                session_id,
            )
        )
        return self.env.cr.fetchone()[0]

    @api.model
    def _try_session_lock(self, session_id: int) -> bool:
        """Try to take a session-scoped advisory lock on the session."""
        self.env.cr.execute(
            SQL(
                'SELECT pg_try_advisory_lock(%s, %s)',
                ADVISORY_LOCK_NAMESPACE,
                session_id,
            )
        )
        return self.env.cr.fetchone()[0]

    @api.model
    def _release_session_lock(self, session_id: int) -> None:
        """Release the session advisory lock, retrying once after rollback."""
        statement = SQL(
            'SELECT pg_advisory_unlock(%s, %s)',
            ADVISORY_LOCK_NAMESPACE,
            session_id,
        )
        try:
            self.env.cr.execute(statement)
            self.env.cr.fetchone()
        except Exception:  # noqa: BLE001 — unlock is best-effort across cursor state
            self.env.cr.rollback()
            with suppress(Exception):
                self.env.cr.execute(statement)
                self.env.cr.fetchone()

    @api.model
    def _claim_dispatch_slot(self) -> int | None:
        """Take one of the shared inline dispatch slots on this cursor.

        Slots are keyed negatively so they can never collide with the
        per-session locks, which share the namespace keyed by session id.

        :return: the claimed slot, or ``None`` when they are all busy
        """
        for slot in range(-1, -DISPATCH_MAX_TURNS - 1, -1):
            self.env.cr.execute(
                SQL(
                    'SELECT pg_try_advisory_lock(%s, %s)',
                    ADVISORY_LOCK_NAMESPACE,
                    slot,
                )
            )
            if self.env.cr.fetchone()[0]:
                return slot
        return None

    @api.model
    def _release_dispatch_slot(self, slot: int) -> None:
        """Give a claimed dispatch slot back, retrying once after rollback.

        :param slot: slot returned by :meth:`_claim_dispatch_slot`
        """
        statement = SQL(
            'SELECT pg_advisory_unlock(%s, %s)',
            ADVISORY_LOCK_NAMESPACE,
            slot,
        )
        try:
            self.env.cr.execute(statement)
            self.env.cr.fetchone()
        except Exception:  # noqa: BLE001 — unlock is best-effort across cursor state
            self.env.cr.rollback()
            with suppress(Exception):
                self.env.cr.execute(statement)
                self.env.cr.fetchone()

    @api.model
    def _dispatch_in_slot(self, session_ids: tuple[int, ...]) -> None:
        """Run the queued turns while holding one of the dispatch slots.

        :param session_ids: sessions to hand to the worker, in queue order
        """
        slot = self._claim_dispatch_slot()
        if slot is None:
            return
        try:
            self._dispatch_queued_turns(session_ids)
        finally:
            self._release_dispatch_slot(slot)

    def _heartbeat_claim(self) -> None:
        """Refresh the worker claim timestamp and commit safely."""
        if self:
            self.sudo().write({'claimed_at': fields.Datetime.now()})
            self._commit_safe()

    # ----------------------------------------------------------
    # Helper Rate Limit
    # ----------------------------------------------------------

    @api.model
    def _get_rate_limit(self) -> int:
        """Return the default provider's per-minute session rate limit."""
        provider = self.env['muk_ai.provider']._get_default()
        return max(0, provider.rate_limit or 0) if provider else 0

    @api.model
    def _check_rate_limit(self, batch_size: int = 1) -> None:
        """Raise when creating ``batch_size`` sessions exceeds the rate limit.

        :raise UserError: when the per-minute rate limit would be exceeded
        """
        if limit := self._get_rate_limit():
            count = self.sudo().search_count(
                [
                    ('user_id', '=', self.env.user.id),
                    ('create_date', '>=', fields.Datetime.now() - timedelta(minutes=1)),
                ]
            )
            if count + batch_size > limit:
                raise UserError(
                    _(
                        'Rate limit reached (%(count)s sessions in the last minute.',
                        count=count,
                    )
                )

    # ----------------------------------------------------------
    # Helper Tool Dispatch
    # ----------------------------------------------------------

    def _tool_dispatch_context(self) -> dict:
        """Return the context keys threaded through tool dispatch."""
        return {'muk_mcp_session_id': self.id}

    def _dispatch_tool_call(self, name: str, arguments: dict, call_id: str) -> tuple:
        """Execute a tool call and return its output and success flag."""
        if name == 'tool_load':
            output = self._dispatch_tool_load(arguments, parent_call_id=call_id)
            return output, 'error' not in output
        enforce_scope = 'read' if self.agent_id and self.agent_id.read_only else None
        arguments, resolved_refs = self._resolve_value_refs(arguments)
        try:
            tool_env = self.env(
                context={**self.env.context, **self._tool_dispatch_context()}
            )
            text, _info = tool_env['muk_mcp.tool']._call(
                name, arguments, tool_env, enforce_scope=enforce_scope
            )
        except Exception as error:  # noqa: BLE001 — report any tool failure to the LLM
            return {'error': str(error)}, False
        self._maybe_publish_ui_action(text, name, call_id)
        if previews := [
            r['preview_url'] for r in resolved_refs if r.get('preview_url')
        ]:
            if isinstance(text, str):
                text += '\n\n' + '\n\n'.join(f'![image set]({u})' for u in previews)
            elif isinstance(text, dict):
                text = {**text, 'image_previews': previews}
        return text, True

    @staticmethod
    def _resolve_tool_name(name: str, known: Container) -> str | None:
        """Match a requested tool name against ``known``, tolerating a namespace prefix."""
        if name in known:
            return name
        if '.' in name and (bare := name.rpartition('.')[2]) in known:
            return bare
        return None

    def _dispatch_tool_load(
        self, arguments: dict, parent_call_id: str | None = None
    ) -> dict:
        """Load tool schemas by name and optionally run an inline call."""
        bad_names = {
            'error': "Argument 'names' must be a non-empty list of tool name strings."
        }
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
        catalog_by_name = {
            entry['name']: entry for entry in self._get_filtered_catalog()
        }
        loaded = {}
        unknown = []
        for name in names:
            if resolved := self._resolve_tool_name(name, catalog_by_name):
                entry = catalog_by_name[resolved]
                loaded[resolved] = {
                    'description': entry.get('description') or '',
                    'inputSchema': (
                        entry.get('inputSchema') or {'type': 'object', 'properties': {}}
                    ),
                }
            else:
                unknown.append(name)
        if loaded:
            self.write(
                {
                    'expanded_tool_names': list(
                        dict.fromkeys(
                            list(self.expanded_tool_names or []) + list(loaded)
                        )
                    )
                }
            )
        response = {'loaded': loaded, 'unknown': unknown}
        if unknown and not loaded:
            response['error'] = (
                'No name resolved to a tool this session can call: '
                f'{", ".join(unknown)}. Use the exact names from the '
                '<available_tools> block, with no namespace prefix. Tools '
                'already in your tools array are callable directly and must '
                'not be loaded.'
            )
        if call_spec := (
            arguments.get('call') if isinstance(arguments, dict) else None
        ):
            response['call'] = self._dispatch_tool_load_inline_call(
                call_spec, loaded, parent_call_id
            )
        return response

    def _dispatch_tool_load_inline_call(
        self, call_spec, loaded: dict, parent_call_id: str | None
    ) -> dict:
        """Execute a tool call bundled into a ``tool_load`` request.

        The file payload is stored here rather than in
        :meth:`_append_tool_output_with_vision`, which only sees the wrapping
        ``tool_load`` response: a nested result would otherwise reach the model
        as raw base64 and be logged to the event stream in full.
        """
        if not isinstance(call_spec, dict):
            return {
                'error': '`call` must be an object with `name` and optional `arguments`.'
            }
        if not (requested := str(call_spec.get('name') or '').strip()):
            return {'error': '`call.name` is required.'}
        if not (target := self._resolve_tool_name(requested, loaded)):
            return {
                'error': (
                    f'`call.name` {requested!r} must be one of the just-loaded names; '
                    'include it in `names` and try again.'
                )
            }
        target_args = call_spec.get('arguments')
        if target_args is None:
            target_args = {
                key: value
                for key, value in call_spec.items()
                if key not in ('name', 'arguments')
            }
        if not isinstance(target_args, dict):
            return {'error': '`call.arguments` must be an object.'}
        inline_call_id = f'{parent_call_id or "tool_load"}__{target}'
        call = {'name': target, 'arguments': target_args, 'call_id': inline_call_id}
        self._record_tool_call(call)
        gate = self._check_approval_gate(target, target_args)
        if gate['action'] == 'pause':
            result = {
                'error': 'requires_approval',
                'reason': gate['risk'].get('reason') or '',
            }
            ok = False
        else:
            if gate['action'] == 'auto_approved':
                self._record_approval_audit(
                    decision='auto_approved', call=call, risk=gate['risk']
                )
            result, ok = self._dispatch_tool_call(target, target_args, inline_call_id)
            result = self._persist_tool_file(result)
        event = {
            'kind': 'tool_result',
            'name': target,
            'result': result,
            'call_id': inline_call_id,
        }
        if sources := extract_sources(target, target_args, result):
            event['sources'] = sources
        self._append_event(event)
        return {'name': target, 'output': result, 'ok': ok}

    def _maybe_publish_ui_action(self, text, name: str, call_id: str) -> None:
        """Publish a UI action when a tool returns an Odoo action payload."""
        try:
            action = json.loads(text) if isinstance(text, str) else None
        except ValueError:
            action = None
        if (
            isinstance(action, dict)
            and isinstance(t := action.get('type'), str)
            and t.startswith('ir.actions.')
        ):
            self._publish_event(
                'ui_action', {'call_id': call_id, 'name': name, 'action': action}
            )
            if name in self._get_terminating_tools():
                self._apply_ui_action(name, action)

    # ----------------------------------------------------------
    # Helper View Context
    # ----------------------------------------------------------

    def _apply_ui_action(self, tool_name: str, action: dict) -> None:
        """Pin the view context derived from a terminating UI action."""
        if payload := self._view_context_from_action(tool_name, action):
            self._write_view_context(payload)

    def _view_context_from_action(self, tool_name: str, action: dict) -> dict | None:
        """Derive a view-context payload from an Odoo action, or ``None``."""
        if isinstance(action, dict) and (res_model := action.get('res_model')):
            if tool_name == 'open_record' or action.get('view_mode') == 'form':
                if res_id := action.get('res_id'):
                    record = self.env[res_model].browse(int(res_id)).exists()
                    return {
                        'kind': 'record',
                        'model': res_model,
                        'id': int(res_id),
                        'display_name': (
                            has_access(record, 'read') and record.display_name
                        )
                        or str(res_id),
                    }
            else:
                payload = {
                    'kind': 'list',
                    'model': res_model,
                    'view_type': (action.get('view_mode') or '').split(',')[0]
                    or 'tree',
                }
                if isinstance(domain := action.get('domain'), list) and domain:
                    payload['domain'] = domain
                if (action_id := action.get('id')) and tool_name == 'open_action':
                    payload.update(kind='action', action_id=action_id)
                return payload
        return None

    def _enrich_view_context(self, payload: dict) -> dict:
        """Return the view-context payload, optionally enriched by subclasses."""
        return payload

    def _write_view_context(self, payload: dict | None) -> None:
        """Persist the view context and broadcast its change."""
        if payload:
            payload = self._enrich_view_context(payload)
        self.write({'view_context': payload or False})
        self._publish_event('view_context', {'view_context': payload or None})

    # ----------------------------------------------------------
    # Helper Streaming
    # ----------------------------------------------------------

    def _check_cancelled(self, buffer_state: dict) -> None:
        """Persist partial output and heartbeat, raising when cancelled.

        :raise StreamCancelled: when the session has been stopped
        """
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

    def _on_stream_delta(self, kind: str, payload: dict, buffer_state: dict) -> None:
        """Coalesce and publish a streamed delta of the given kind."""
        self._check_cancelled(buffer_state)
        if kind == 'text':
            if delta := (payload or {}).get('delta') or '':
                buffer_state['full_text'] = buffer_state.get('full_text', '') + delta
                self._coalesce_and_emit(
                    buffer_state, 'text', 'last_text_flush', delta, 'text_delta'
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
            self._publish_event(
                'tool_call_start',
                {
                    'call_id': payload.get('call_id'),
                    'name': payload.get('name'),
                },
            )
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
        buffer_state: dict,
        content_key: str,
        last_key: str,
        delta: str,
        event_type: str,
        extra: dict | None = None,
    ) -> None:
        """Buffer a delta and emit it once size or time thresholds are met."""
        now = time.monotonic()
        buffer_state.setdefault(content_key, '')
        buffer_state.setdefault(last_key, now)
        buffer_state[content_key] += delta
        if (
            len(buffer_state[content_key]) >= 80
            or (now - buffer_state[last_key]) >= 0.1
        ):
            flushed = buffer_state[content_key]
            buffer_state[content_key] = ''
            buffer_state[last_key] = now
            self._publish_event(event_type, {'delta': flushed, **(extra or {})})
            self._commit_safe()

    def _flush_text_buffer(self, buffer_state: dict) -> None:
        """Flush any buffered text delta to the bus."""
        if flushed := buffer_state.get('text'):
            buffer_state['text'] = ''
            self._publish_event('text_delta', {'delta': flushed})
            self._commit_safe()

    def _persist_partial(self, buffer_state: dict) -> None:
        """Persist buffered assistant text as a partial conversation message."""
        if text := buffer_state.get('full_text'):
            self.write(
                {
                    'last_text': text,
                    'conversation': [
                        *(self.conversation or []),
                        {
                            'type': 'message',
                            'role': 'assistant',
                            'content': [{'type': 'output_text', 'text': text}],
                        },
                    ],
                }
            )
            self._append_event({'kind': 'text', 'content': text})
            self.flush_recordset()

    def _flush_stream_buffer(self, buffer_state: dict) -> None:
        """Flush all remaining text, reasoning, and tool-arg buffers."""
        self._flush_text_buffer(buffer_state)
        if flushed := buffer_state.get('reasoning'):
            buffer_state['reasoning'] = ''
            self._publish_event('reasoning_delta', {'delta': flushed})
        for key in list(buffer_state.keys()):
            if key.startswith('tool_args_') and not key.endswith('_last'):
                if flushed := buffer_state.get(key):
                    buffer_state[key] = ''
                    self._publish_event(
                        'tool_call_args_delta',
                        {
                            'call_id': key[len('tool_args_') :],
                            'delta': flushed,
                        },
                    )
        self._commit_safe()

    def _materialize_round_inputs(
        self,
        provider: models.BaseModel,
        cache: dict,
        notice: dict | None = None,
    ) -> list:
        """Materialize attachment blocks for a round, caching by attachment id."""
        materialized = []
        for item in self._build_request_inputs():
            content = item.get('content') if isinstance(item, dict) else None
            if not isinstance(content, list):
                materialized.append(item)
                continue
            blocks = []
            for block in content:
                if is_unmaterialized_attachment(block):
                    key = block.get('attachment_id')
                    if key is None:
                        block = provider._materialize_block(block)
                    else:
                        if key not in cache:
                            cache[key] = provider._materialize_block(block)
                        block = cache[key]
                blocks.append(block)
            materialized.append({**item, 'content': blocks})
        if notice:
            materialized.append(notice)
        return materialized

    def _stream_provider_round(
        self,
        provider: models.BaseModel,
        tool_schema: list,
        model: str | None,
        agent: models.BaseModel,
        cache: dict | None = None,
        notice: dict | None = None,
    ) -> dict:
        """Run one streaming provider round, flushing buffers on completion.

        :raise StreamCancelled: when the session is cancelled mid-stream
        """
        buffer_state = {'text': '', 'last_text_flush': time.monotonic()}
        try:
            payload = provider._request_responses(
                inputs=self._materialize_round_inputs(
                    provider,
                    {} if cache is None else cache,
                    notice=notice,
                ),
                tools_schema=tool_schema,
                model=model,
                on_delta=lambda kind, data: self._on_stream_delta(
                    kind, data, buffer_state
                ),
                reasoning_effort=agent.reasoning_effort if agent else None,
                enable_web_search=bool(agent and agent.enable_web_search),
                enable_image_generation=bool(agent and agent.enable_image_generation),
                enable_code_interpreter=bool(agent and agent.enable_code_interpreter),
                cache_key=f'muk_ai.session:{self.id}',
            )
            self._flush_stream_buffer(buffer_state)
            return payload
        except StreamCancelled:
            self._flush_stream_buffer(buffer_state)
            raise

    # ----------------------------------------------------------
    # Auto-name
    # ----------------------------------------------------------

    def _autoname_from_text(self, raw: str) -> str:
        """Derive a short session title from the first sentence of text."""
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

    def _accrue_cost_deltas(self, usage: dict | None) -> dict:
        """Return the cumulative cost field deltas for a usage payload."""
        if record := self._effective_model_record():
            delta = record._compute_usage_cost(usage or {})
            return {
                'total_input_cost': (self.total_input_cost or 0.0)
                + delta['input_cost'],
                'total_output_cost': (self.total_output_cost or 0.0)
                + delta['output_cost'],
                'total_cost': (self.total_cost or 0.0) + delta['total_cost'],
                'turn_cost_spent': (self.turn_cost_spent or 0.0) + delta['total_cost'],
            }
        return {}

    def _persist_inline_images(self, text: str, cache: dict | None = None) -> str:
        """Replace inline base64 images with stored attachment references."""
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
                        attachment = (
                            self.env['ir.attachment']
                            .sudo()
                            ._ai_create_from_upload(
                                alt or 'generated.png',
                                mimetype,
                                b64,
                                res_id=self.id,
                            )
                        )
                    except Exception:  # noqa: BLE001 — keep raw image on store failure
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

    def _persist_inline_images_in_carry(self, items: list | None, cache: dict) -> list:
        """Persist inline images inside carried conversation items."""
        out = []
        for item in items or []:
            if isinstance(item, dict) and isinstance(
                content := item.get('content'), list
            ):
                out.append(
                    {
                        **item,
                        'content': [
                            {
                                **c,
                                'text': self._persist_inline_images(
                                    c['text'], cache=cache
                                ),
                            }
                            if isinstance(c, dict)
                            and isinstance(c.get('text'), str)
                            and 'data:image/' in c['text']
                            else c
                            for c in content
                        ],
                    }
                )
            else:
                out.append(item)
        return out

    def _vision_enabled(self) -> bool:
        """Return whether the effective provider can consume image inputs."""
        provider = self._effective_provider()
        return bool(provider and provider.supports_vision)

    @staticmethod
    def _image_content_blocks(content) -> list:
        """Return the image blocks from an MCP-style content list."""
        if not isinstance(content, list):
            return []
        return [
            block
            for block in content
            if isinstance(block, dict) and block.get('type') == 'image'
        ]

    def _collect_tool_image_specs(self, result) -> list:
        """Return normalized image specs a tool result carries.

        Supports the ``{'images': [{'data', 'mimetype', 'name'}, ...]}``
        convention and MCP image content blocks
        (``{'type': 'image', 'data', 'mimeType'}``).
        """
        blocks = []
        if isinstance(result, dict):
            blocks += [b for b in (result.get('images') or []) if isinstance(b, dict)]
            blocks += self._image_content_blocks(result.get('content'))
        elif isinstance(result, list):
            blocks += self._image_content_blocks(result)
        specs = []
        for block in blocks:
            data = block.get('data') or block.get('data_b64')
            if not isinstance(data, str) or not data:
                continue
            specs.append(
                {
                    'data': re.sub(r'\s+', '', data),
                    'mimetype': (
                        block.get('mimetype') or block.get('mimeType') or 'image/png'
                    ),
                    'name': (
                        block.get('name') or block.get('filename') or 'tool-image.png'
                    ),
                }
            )
        return specs

    def _strip_tool_images(self, result) -> object:
        """Return the tool result with inline image payloads removed."""
        if isinstance(result, dict):
            cleaned = {key: value for key, value in result.items() if key != 'images'}
            if isinstance(cleaned.get('content'), list):
                cleaned['content'] = [
                    block
                    for block in cleaned['content']
                    if not (isinstance(block, dict) and block.get('type') == 'image')
                ]
            return cleaned
        if isinstance(result, list):
            return [
                block
                for block in result
                if not (isinstance(block, dict) and block.get('type') == 'image')
            ]
        return result

    def _persist_tool_image(self, spec: dict) -> models.BaseModel:
        """Persist one tool image spec as a session attachment, or skip on error."""
        empty = self.env['ir.attachment']
        if spec['mimetype'] not in IMAGE_MIMETYPES:
            return empty
        data = spec['data']
        if data.startswith('data:') and ',' in data:
            data = data.split(',', 1)[1]
        if not data or len(data) > TOOL_VISION_MAX_B64_CHARS:
            return empty
        try:
            return (
                self.env['ir.attachment']
                .sudo()
                ._ai_create_from_upload(
                    spec['name'], spec['mimetype'], data, res_id=self.id
                )
            )
        except UserError:
            return empty

    def _extract_tool_vision(self, result) -> tuple[models.BaseModel, object]:
        """Pop image payloads from a tool result and persist them as attachments.

        :return: the created attachments and the text-only result to send back
            as the ``function_call_output``
        """
        empty = self.env['ir.attachment']
        specs = self._collect_tool_image_specs(result)
        if not specs:
            return empty, result
        if not self._vision_enabled():
            return empty, self._note_vision_unavailable(self._strip_tool_images(result))
        attachments = empty
        for spec in specs[:TOOL_VISION_MAX_IMAGES]:
            attachments |= self._persist_tool_image(spec)
        cleaned = self._strip_tool_images(result)
        if not attachments:
            cleaned = self._note_vision_unavailable(cleaned)
        return attachments, cleaned

    @staticmethod
    def _note_vision_unavailable(cleaned) -> object:
        """Append a note when a tool's images could not be shown to the model."""
        note = (
            'Note: images were produced but cannot be shown to this model; '
            'rely on the textual/structural result instead.'
        )
        if isinstance(cleaned, dict):
            text = cleaned.get('text')
            return {**cleaned, 'text': f'{text}\n{note}' if text else note}
        return cleaned

    def _persist_tool_file(self, result) -> object:
        """Store a tool's file payload and swap its base64 for a download URL.

        A file-producing tool answers with ``content_base64``. Left in place it
        floods the context window and still leaves the model no way to hand the
        file over, which is why models resort to inventing ``data:`` links. The
        bytes become a session attachment instead, and the result carries the
        ``/web/content`` URL the chat renderer accepts.

        The registry JSON-encodes a tool's dict result, so the payload usually
        arrives as text and is decoded before the swap. The reported mimetype
        is the stored one, not the transport content type the tool sent, so
        the chat resolves the same preview the attachment itself would.
        """
        if isinstance(result, str):
            if 'content_base64' not in result:
                return result
            try:
                parsed = json.loads(result)
            except ValueError:
                return result
            stored = self._persist_tool_file(parsed)
            return result if stored is parsed else json.dumps(stored, indent=2)
        if not (payload := tool_file_payload(result)):
            return result
        rest = {key: value for key, value in result.items() if key != 'content_base64'}
        try:
            attachment = (
                self.env['ir.attachment']
                .sudo()
                ._ai_store_binary(
                    payload['filename'],
                    payload['mimetype'],
                    payload['data_b64'],
                    res_id=self.id,
                )
            )
        except UserError as error:
            return {**rest, 'error': str(error)}
        return {
            **rest,
            'mimetype': attachment.mimetype,
            'attachment_id': attachment.id,
            'url': f'/web/content/{attachment.id}?download=1',
        }

    def _bound_tool_output(self, entry: dict) -> dict:
        """Cap an oversized tool output so one result can't exhaust the window.

        The character budget is the raw context-window size, i.e. roughly a
        quarter of it in tokens (~4 chars per token). Only the model-facing
        copy is bounded; the full result is still logged to the event for the
        client. The marker tells the model the data was truncated so it can
        narrow the query or aggregate instead of failing the whole request
        with a provider ``input too large`` error.
        """
        text = entry.get('output')
        if not isinstance(text, str):
            return entry
        max_chars = self._resolve_context_window()
        if len(text) <= max_chars:
            return entry
        dropped = len(text) - max_chars
        return {
            **entry,
            'output': (
                f'{text[:max_chars]}\n\n[... tool result truncated: {dropped} of '
                f'{len(text)} characters dropped to fit the context window. '
                'Narrow the query with filters or a limit, or use aggregation '
                'to retrieve the rest.]'
            ),
        }

    def _append_tool_output_with_vision(
        self, outputs: list, call_id: str, result
    ) -> object:
        """Append a tool output and defer any image payload for the round.

        Any file payload is stored first, so the ``function_call_output`` never
        carries raw base64. The text-only result becomes the
        ``function_call_output`` immediately.
        Image attachments are held on the session (not appended inline) and
        flushed by ``_flush_deferred_vision`` once every function_call_output of
        the round is emitted, so images always follow all tool results across a
        pause/resume boundary (providers reject a tool_result after other user
        content).

        :return: the cleaned, text-only result for event logging
        """
        attachments, cleaned = self._extract_tool_vision(
            self._persist_tool_file(result)
        )
        outputs.append(
            self._bound_tool_output(build_tool_call_output(call_id, cleaned))
        )
        if attachments:
            deferred = list(self.deferred_vision_attachment_ids or [])
            deferred += [a.id for a in attachments if a.id not in deferred]
            self.deferred_vision_attachment_ids = deferred
        return cleaned

    def _flush_deferred_vision(self, outputs: list) -> list:
        """Return ``outputs`` with the round's deferred vision images appended.

        Emits a single trailing user entry carrying every image a tool produced
        this round, then clears the buffer. A no-op when nothing was deferred.
        """
        ids = list(self.deferred_vision_attachment_ids or [])
        if not ids:
            return outputs
        attachments = self.env['ir.attachment'].browse(ids).exists()
        self.deferred_vision_attachment_ids = False
        entry = self._build_user_entry(None, attachments)
        if not entry:
            return outputs
        return [*outputs, {**entry, '_vision_entry': True}]

    @staticmethod
    def _order_round_outputs(outputs: list) -> list:
        """Return round outputs with tool results first and user entries last.

        Keeps every ``function_call_output`` contiguous after the assistant's
        tool calls, appending any injected vision user entries afterwards.
        """
        tool_outputs = [
            item
            for item in outputs
            if isinstance(item, dict) and item.get('type') == 'function_call_output'
        ]
        others = [
            item
            for item in outputs
            if not (
                isinstance(item, dict) and item.get('type') == 'function_call_output'
            )
        ]
        return tool_outputs + others

    def _resolve_value_refs(self, arguments: dict) -> tuple[dict, list]:
        """Inline attachment and URL references in tool arguments.

        :return: the resolved arguments and the list of resolved reference
            descriptors carrying preview URLs
        """
        refs = []
        if isinstance(arguments, dict):

            def _resolve(value):
                if isinstance(value, str):
                    if m := ATTACHMENT_REF_RE.match(value):
                        attachment = self.env['ir.attachment'].browse(int(m.group(1)))
                        if not attachment.exists():
                            return value
                        try:
                            attachment.check_access_rights('read')
                            attachment.check_access_rule('read')
                        except AccessError:
                            return value
                        attachment = attachment.sudo()
                        if (
                            attachment.datas
                            and attachment.file_size <= ATTACHMENT_REF_MAX_BYTES
                            and (
                                not attachment.mimetype
                                or attachment.mimetype in ALLOWED_MIMETYPES
                            )
                        ):
                            refs.append(
                                {
                                    'kind': 'attachment',
                                    'preview_url': f'/web/image/{attachment.id}',
                                }
                            )
                            return attachment.datas.decode()
                        return value
                    if m := URL_REF_RE.match(value):
                        url = m.group(1)
                        try:
                            result = fetch_url(url)
                        except (UserError, urllib3.exceptions.HTTPError):
                            return value
                        refs.append({'kind': 'url', 'preview_url': url})
                        return base64.b64encode(result.body).decode()
                    return value
                if isinstance(value, dict):
                    return {k: _resolve(v) for k, v in value.items()}
                if isinstance(value, list):
                    return [_resolve(v) for v in value]
                return value

            return _resolve(arguments), refs
        return arguments, refs

    def _accrue_usage(self, usage: dict | None) -> None:
        """Accumulate token counts and costs from a round's usage payload."""
        usage = usage or {}
        round_input_tokens = usage.get('input_tokens')
        self.write(
            {
                'iteration_count': self.iteration_count + 1,
                'total_input_tokens': self.total_input_tokens
                + (round_input_tokens or 0),
                'total_output_tokens': self.total_output_tokens
                + usage.get('output_tokens', 0),
                'last_input_tokens': (
                    self.last_input_tokens
                    if round_input_tokens is None
                    else round_input_tokens
                ),
                **self._accrue_cost_deltas(usage),
            }
        )

    def _accrue_round_payload(self, payload: dict) -> None:
        """Accrue usage and persist text and carried inputs from a round."""
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

    def _finalize_round(self, payload: dict) -> None:
        """Transition to done or error based on the round's text output."""
        if payload.get('text'):
            self._transition_state('done')
        else:
            self._transition_state('error', error=_('AI returned no output.'))

    def _skip_reason(
        self,
        has_ask_user: bool,
        has_terminating: bool,
        has_client_action: bool = False,
    ) -> str | None:
        """Return why remaining tool calls should be skipped, or ``None``."""
        if has_ask_user:
            return 'skipped: ask_user pending, call again after user answer'
        if has_client_action:
            return (
                'skipped: client action pending, call again after the client responds'
            )
        if has_terminating:
            return (
                'skipped: terminating tool already ran; emit a short summary and stop'
            )
        return None

    def _record_tool_call(self, call: dict) -> None:
        """Record a tool-call event with any subclass-provided extras."""
        event = {
            'kind': 'tool_call',
            'name': call['name'],
            'arguments': call['arguments'],
            'call_id': call['call_id'],
        }
        event.update(self._tool_call_event_extra(call))
        self._append_event(event)

    def _tool_call_event_extra(self, call: dict) -> dict:
        """Return extra fields to attach to a tool-call event."""
        return {}

    def _skip_tool_call(
        self, outputs: list, call: dict, reason: str, log_result=None
    ) -> None:
        """Record a skipped tool call and emit a synthetic denied result."""
        result = {'error': reason}
        self._persist_synthetic_event(call, result, 'denied')
        self._record_tool_result(
            outputs, call['call_id'], call['name'], result, log_result=log_result
        )

    def _client_tool_names(self) -> set[str]:
        """Return the catalog tool names the client must execute.

        Overridable hook: the default scans the registry catalog once and
        treats ``meta.execute == 'client'`` as client-executed.
        """
        return {
            entry['name']
            for entry in self._get_filtered_catalog()
            if entry.get('name')
            and (entry.get('_meta') or {}).get('execute') == 'client'
        }

    def _is_client_tool(self, name: str) -> bool:
        """Return whether the named tool must be executed by the client."""
        return bool(name) and name in self._client_tool_names()

    def _client_action_deferred(self, call: dict) -> str | None:
        """Return a skip reason when the call cannot join the open action batch.

        Overridable hook: subclasses that gate individual client actions
        (e.g. behind an approval) return a reason so the call is skipped
        instead of clobbering the already pending batch.
        """
        return None

    def _client_action_with_cursor(self, pending: dict) -> dict:
        """Return the pending dict with the first unanswered action mirrored.

        The mirrored ``call_id``/``name``/``arguments`` keys keep
        single-action consumers working while ``actions``/``results``
        carry the batch.
        """
        results = pending.get('results') or {}
        cursor = next(
            (
                action
                for action in (pending.get('actions') or [])
                if action.get('call_id') not in results
            ),
            None,
        )
        for key in ('call_id', 'name', 'arguments'):
            pending.pop(key, None)
        if cursor:
            pending.update(
                {
                    'call_id': cursor['call_id'],
                    'name': cursor['name'],
                    'arguments': cursor['arguments'],
                }
            )
        return pending

    def _register_client_action(self, call: dict) -> None:
        """Append a pending client-executed tool call awaiting the client."""
        pending = dict(self.pending_ask or {})
        if pending.get('kind') != 'client_action':
            pending = {
                'kind': 'client_action',
                'registered_at': fields.Datetime.to_string(fields.Datetime.now()),
                'actions': [],
                'results': {},
            }
        pending['actions'] = [
            *(pending.get('actions') or []),
            {
                'call_id': call['call_id'],
                'name': call['name'],
                'arguments': call['arguments'],
            },
        ]
        self.pending_ask = self._client_action_with_cursor(pending)
        self._record_tool_call(call)
        self._append_event(
            {
                'kind': 'client_action',
                'call_id': call['call_id'],
                'name': call['name'],
                'arguments': call['arguments'],
            }
        )

    def _register_ask_user(self, call: dict) -> None:
        """Register a pending question from an ``ask_user`` tool call."""
        args = call['arguments'] or {}
        ask = {
            'call_id': call['call_id'],
            'text': args.get('question'),
            'options': args.get('options'),
            'resolution': args.get('resolution') or 'text',
            'preview': clean_ask_preview(args.get('preview')),
        }
        self.pending_ask = {'kind': 'question', **ask}
        self._append_event({'kind': 'ask_user', **ask})

    def _resume_turn(self, continuation: list, event: dict | None = None) -> None:
        """Append a pause's continuation and event, clear it, and resume the turn."""
        self._extend_conversation(continuation)
        if event:
            self._append_event(event)
        self.write(
            {
                'state': 'running',
                'pending_ask': False,
                'claimed_at': False,
                'turn_wallclock_spent': 0.0,
                'turn_cost_spent': 0.0,
            }
        )
        self._publish_event('state', {'state': 'running'})
        self._trigger_worker()

    def _require_pending_client_action(self, call_id: str | None = None) -> dict:
        """Return the pending client action batch, validating state and call id.

        :raise UserError: when the session is not awaiting this client action
        """
        pending = dict(self.pending_ask or {})
        if self.state != 'waiting' or pending.get('kind') != 'client_action':
            raise UserError(_('Session is not waiting for a client action.'))
        if call_id is None:
            return pending
        results = pending.get('results') or {}
        unanswered = {
            action.get('call_id')
            for action in (pending.get('actions') or [])
            if action.get('call_id') not in results
        }
        if call_id not in unanswered:
            raise UserError(_('Client action call id does not match a pending action.'))
        return pending

    def _apply_client_result(self, pending: dict, call_id: str, result) -> None:
        """Record one client tool result and resume once the batch completes."""
        actions = pending.get('actions') or []
        named = next(
            (action for action in actions if action.get('call_id') == call_id),
            {},
        )
        pending['results'] = {**(pending.get('results') or {}), call_id: result}
        self._append_event(
            {
                'kind': 'client_action_result',
                'call_id': call_id,
                'name': named.get('name'),
                'result': self._strip_tool_images(result),
            }
        )
        if any(action.get('call_id') not in pending['results'] for action in actions):
            self.pending_ask = self._client_action_with_cursor(pending)
            self._publish_event(
                'state',
                {'state': 'waiting', 'ask': self._public_pending_ask()},
            )
            return
        continuation = []
        for action in actions:
            self._append_tool_output_with_vision(
                continuation, action['call_id'], pending['results'][action['call_id']]
            )
        self._resume_turn(
            self._flush_deferred_vision(self._order_round_outputs(continuation))
        )

    def _execute_tool_call(
        self,
        call: dict,
        tool_calls: list,
        outputs: list,
        index: int,
        has_terminating: bool,
    ) -> bool | None:
        """Run one tool call, handling approval gating and result recording."""
        gate = self._check_approval_gate(call['name'], call['arguments'])
        if gate['action'] == 'pause':
            self._enter_waiting_approval(
                call, tool_calls, outputs, index, has_terminating, gate
            )
            return None
        self._record_tool_call(call)
        if gate['action'] == 'auto_approved':
            self._record_approval_audit(
                decision='auto_approved', call=call, risk=gate['risk']
            )
        self._heartbeat_claim()
        result, ok = self._dispatch_tool_call(
            call['name'], call['arguments'], call['call_id']
        )
        self._heartbeat_claim()
        self._record_tool_result(
            outputs, call['call_id'], call['name'], result, arguments=call['arguments']
        )
        return ok and call['name'] in self._get_terminating_tools()

    def _process_tool_round(
        self,
        tool_calls: list,
        outputs: list,
        start_index: int,
        has_terminating: bool = False,
    ) -> bool | None:
        """Run a round of tool calls, returning the terminating state or ``None``."""
        has_ask_user = any(c.get('name') == 'ask_user' for c in tool_calls)
        wait_for_user, paused = False, False
        client_names = self._client_tool_names()
        for index in range(start_index, len(tool_calls)):
            call = tool_calls[index]
            if index >= MAX_TOOL_CALLS_PER_ROUND:
                self._record_tool_call(call)
                self._skip_tool_call(
                    outputs,
                    call,
                    'tool_call_limit_exceeded',
                    log_result={'error': 'tool_call_limit_exceeded'},
                )
                continue
            if call.get('_parse_error'):
                self._record_tool_call(call)
                self._skip_tool_call(outputs, call, call['_parse_error'])
                continue
            if call['name'] == 'ask_user':
                if wait_for_user:
                    self._record_tool_call(call)
                    self._skip_tool_call(
                        outputs,
                        call,
                        'ask_user_already_pending',
                        log_result={'error': 'ask_user_already_pending'},
                    )
                    continue
                self._register_ask_user(call)
                wait_for_user = True
                continue
            if (
                not has_ask_user
                and not has_terminating
                and call['name'] in client_names
            ):
                batch_open = (
                    wait_for_user
                    and (self.pending_ask or {}).get('kind') == 'client_action'
                )
                skip = None
                if wait_for_user and not batch_open:
                    skip = 'client_action_already_pending'
                elif batch_open:
                    skip = self._client_action_deferred(call)
                if skip:
                    self._record_tool_call(call)
                    self._skip_tool_call(
                        outputs, call, skip, log_result={'error': skip}
                    )
                    continue
                self._register_client_action(call)
                wait_for_user = True
                continue
            if skip := self._skip_reason(
                has_ask_user, has_terminating, has_client_action=wait_for_user
            ):
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
            if call['name'] == TOOL_LOAD_TOOL['name']:
                client_names = self._client_tool_names()
        if not paused:
            ordered = self._order_round_outputs(outputs)
            if not wait_for_user:
                ordered = self._flush_deferred_vision(ordered)
            self._extend_conversation(ordered)
            if wait_for_user:
                self.write({'state': 'waiting'})
                self._publish_event(
                    'state',
                    {
                        'state': 'waiting',
                        'ask': self._public_pending_ask(),
                    },
                )
        return None if paused or wait_for_user else has_terminating

    def _turn_budget_error(self, turn_budget: float) -> None:
        """Transition to error when the turn wallclock budget is exhausted."""
        self._transition_state(
            'error',
            error=_(
                'Turn wallclock budget reached (%(s)s s). Send a new message to continue.',
                s=int(turn_budget),
            ),
        )

    def _cost_currency(self) -> str:
        """Return the currency of the effective model, defaulting to USD."""
        record = self._effective_model_record()
        return (record and record.currency) or 'USD'

    def _turn_cost_error(self, limit: float) -> None:
        """Transition to error when the turn cost budget is reached."""
        self._transition_state(
            'error',
            error=_(
                'Turn cost budget reached (%(amount).2f %(currency)s). '
                'Send a new message to continue.',
                amount=limit,
                currency=self._cost_currency(),
            ),
        )

    def _round_limit_notice(self, remaining: int | None) -> dict | None:
        """Build a user-visible notice about remaining round and cost budget."""
        parts = []
        if remaining is not None:
            parts.append(f'Only {remaining} tool round(s) remain for this turn.')
        if limit := self._turn_cost_limit():
            spent = self.turn_cost_spent or 0.0
            if spent >= 0.8 * limit:
                currency = self._cost_currency()
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

    def _yield_slice(self) -> None:
        """Commit and trigger a worker cron to continue the turn elsewhere."""
        if modules.module.current_test:
            return
        self._commit_safe()
        if crons := self._session_worker_crons():
            with suppress(Exception):
                random.choice(crons)._trigger()

    def _handle_wallclock_expiry(
        self, slice_start: float, spent_before: float, turn_budget: float
    ) -> None:
        """Persist spent time and either error out or yield the slice."""
        total = spent_before + (time.monotonic() - slice_start)
        self.write({'turn_wallclock_spent': total})
        if total >= turn_budget:
            self._turn_budget_error(turn_budget)
            return
        self._yield_slice()

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
            self._run_iterations(has_terminating=has_terminating, deadline=deadline)
            if self.state == 'running' and time.monotonic() > deadline:
                self._handle_wallclock_expiry(
                    slice_start,
                    min(spent_before, self.turn_wallclock_spent or 0.0),
                    turn_budget,
                )
                return
            if self.state != 'done':
                return
            if not self._drain_pending_message():
                return
            if time.monotonic() > deadline:
                self._yield_slice()
                return
            self._transition_state('running')
            has_terminating = False

    def _run_iterations(
        self, has_terminating: bool = False, deadline: float | None = None
    ) -> None:
        """Run provider rounds until completion, deadline, or budget limits."""
        deadline = deadline or time.monotonic() + self._slice_wallclock_seconds()
        materialize_cache, provider_key = {}, None
        max_iterations = self._max_iterations()
        for iteration in range(max_iterations):
            if self.state != 'running':
                return
            if time.monotonic() > deadline:
                return
            self._maybe_auto_compact()
            if self.state != 'running':
                return
            if (cost_limit := self._turn_cost_limit()) and (
                (self.turn_cost_spent or 0.0) >= cost_limit
            ):
                self._turn_cost_error(cost_limit)
                return
            self.invalidate_recordset(['pending_ids', 'expanded_tool_names'])
            if self.pending_ids and self._drain_pending_message():
                has_terminating = False
            provider, model = self._effective_provider(), self._effective_model()
            if provider.id != provider_key:
                provider_key, materialize_cache = provider.id, {}
            tool_schema = self._get_tool_schema()
            schema, round_agent = (
                (None, None) if has_terminating else (tool_schema, self.agent_id)
            )
            remaining = max_iterations - iteration
            try:
                payload = self._stream_provider_round(
                    provider,
                    schema,
                    model,
                    round_agent,
                    cache=materialize_cache,
                    notice=self._round_limit_notice(
                        remaining if remaining <= ITERATION_WARNING_ROUNDS else None
                    ),
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
            self._transition_state('error', error=_('Maximum iterations reached.'))

    # ----------------------------------------------------------
    # Queue
    # ----------------------------------------------------------

    def _serialize_pending(self) -> list[dict]:
        """Return the serialized payloads of queued pending messages."""
        return [p._to_payload() for p in self.pending_ids]

    def enqueue_message(
        self, user_message: str | None, attachment_ids: list[int] | None = None
    ) -> dict:
        """Queue a user message and return the session snapshot.

        Locks the session row to serialize against the terminal
        transition of the running turn, whose queue drain would
        otherwise miss a row inserted concurrently. When the locked
        state is already terminal no drain will ever run again, so
        instead of queueing, the snapshot is returned with the marker
        ``queue_rejected_state`` and the caller re-sends the message
        through the regular send path.
        """
        self.ensure_one()
        self.flush_recordset()
        self.env.cr.execute(
            'SELECT state FROM muk_ai_session WHERE id = %s FOR UPDATE',
            [self.id],
        )
        row = self.env.cr.fetchone()
        state = row[0] if row else self.state
        self.invalidate_recordset(['state'])
        if state not in ('running', 'waiting', 'compacting'):
            snapshot = self.get_snapshot()
            snapshot['queue_rejected_state'] = state
            return snapshot
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
        """Remove a queued message by index and return the snapshot."""
        pending = self.pending_ids
        if 0 <= index < len(pending):
            pending[index].unlink()
            self.invalidate_recordset(['pending_ids'])
            self._publish_event('queue', {'pending': self._serialize_pending()})
        return self.get_snapshot()

    def _drain_pending_message(self) -> bool:
        """Merge queued messages into a new turn; return whether any drained."""
        if pending := self.pending_ids:
            contents = [p.content or '' for p in pending]
            attachment_ids = [aid for p in pending for aid in (p.attachment_ids or [])]
            combined = '\n\n'.join(c for c in contents if c.strip())
            attachments = self._resolve_attachments(attachment_ids)
            pending.unlink()
            self.invalidate_recordset(['pending_ids'])
            self._publish_event('queue', {'pending': []})
            self._enqueue_user_turn(combined, attachments)
            return True
        return False

    # ----------------------------------------------------------
    # Helper Approval
    # ----------------------------------------------------------

    def _require_pending_approval(self) -> dict:
        """Return the pending approval payload, or raise when none is active.

        :raise UserError: when the session is not awaiting approval
        """
        pending = dict(self.pending_ask or {})
        if self.state != 'waiting' or pending.get('kind') != 'approval':
            raise UserError(_('Session is not waiting for approval.'))
        return pending

    def _check_approval_gate(self, name: str, arguments: dict) -> dict:
        """Decide whether a tool call dispatches, auto-approves, or pauses."""
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
        call: dict,
        tool_calls: list,
        outputs: list,
        index: int,
        has_terminating: bool,
        gate: dict,
    ) -> None:
        """Pause the round awaiting user approval of a risky tool call."""
        risk = gate['risk']
        preview = (
            self.env['muk_ai.approval']._build_preview(call['name'], call['arguments'])
            or {}
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
        self._append_event(
            {
                'kind': 'ask_user',
                'call_id': call['call_id'],
                'text': risk.get('reason') or '',
                'resolution': 'yesno',
                'preview': preview,
            }
        )
        self.write({'state': 'waiting', 'pending_ask': pending})
        self._publish_event(
            'state',
            {
                'state': 'waiting',
                'ask': self._public_pending_ask(pending),
            },
        )

    def _record_approval_audit(
        self,
        decision: str,
        call: dict,
        risk: dict,
        args_executed: dict | None = None,
        reject_reason: str | None = None,
    ) -> None:
        """Create an approval audit record for a tool-call decision."""
        self.env['muk_ai.approval'].sudo().create(
            {
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
            }
        )

    def _resume_tool_round(
        self, paused: dict, approved: bool, reject_reason: str | None = None
    ) -> None:
        """Resume a paused tool round after an approval decision.

        :raise UserError: when the session lock cannot be acquired
        """
        if not self._try_session_lock(self.id):
            raise UserError(_('The session is currently busy. Please try again.'))
        try:
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
                outputs,
                call['call_id'],
                call['name'],
                result,
                arguments=call['arguments'],
            )
            self.write({'pending_ask': False, 'claimed_at': False})
            self._transition_state('running')
            self._process_tool_round(
                tool_calls,
                outputs,
                paused.get('resume_index', 0) + 1,
                has_terminating=has_terminating,
            )
        finally:
            self._release_session_lock(self.id)

    def _flush_orphaned_tool_outputs(self) -> None:
        """Emit cancelled outputs for tool calls left pending on stop."""
        pending = dict(self.pending_ask or {})
        if not pending:
            return
        outputs = list(pending.get('outputs') or [])
        answered = {
            entry.get('call_id') for entry in outputs if isinstance(entry, dict)
        }
        calls = list(pending.get('tool_calls') or [])
        if not calls:
            calls = [
                {'call_id': action.get('call_id')}
                for action in (pending.get('actions') or [])
            ]
        if not calls and pending.get('call_id'):
            calls = [{'call_id': pending['call_id']}]
        results = pending.get('results') or {}
        for call in calls:
            call_id = call.get('call_id')
            if call_id and call_id not in answered:
                answered.add(call_id)
                outputs.append(
                    build_tool_call_output(
                        call_id,
                        results.get(
                            call_id,
                            {'status': 'cancelled', 'reason': 'stopped_by_user'},
                        ),
                    )
                )
        outputs = self._flush_deferred_vision(self._order_round_outputs(outputs))
        if outputs:
            self._extend_conversation(outputs)

    # ----------------------------------------------------------
    # Helper Compact
    # ----------------------------------------------------------

    def _estimate_entry_tokens(self, entry) -> int:
        """Roughly estimate the token count of a conversation entry."""
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

    def _split_conversation_for_compact(self) -> tuple[list, list]:
        """Split the conversation into a summarizable prefix and a kept tail."""
        keep_budget = max(2000, min(20000, self._resolve_context_window() // 5))
        tail, used = [], 0
        for entry in reversed(self.conversation or []):
            est = self._estimate_entry_tokens(entry)
            if used + est > keep_budget and tail:
                break
            tail.insert(0, entry)
            used += est
        while tail and not (
            isinstance(tail[0], dict) and tail[0].get('role') == 'user'
        ):
            tail.pop(0)
        prefix = (
            (self.conversation or [])[: -len(tail)]
            if tail
            else list(self.conversation or [])
        )
        if not prefix or not tail:
            conversation = list(self.conversation or [])
            split = max(
                (
                    index
                    for index, entry in enumerate(conversation)
                    if isinstance(entry, dict) and entry.get('role') == 'user'
                ),
                default=None,
            )
            if split is None:
                prefix, tail = conversation, []
            else:
                prefix, tail = conversation[:split], conversation[split:]
        return prefix, tail

    def _find_prior_compact_summary(self) -> str | None:
        """Return the most recent prior compaction summary, if any."""
        if not self.id:
            return None
        prior = (
            self.env['muk_ai.session.event']
            .sudo()
            .search(
                [
                    ('session_id', '=', self.id),
                    ('kind', 'in', ('compact_progress', 'command')),
                ],
                order='sequence desc',
                limit=5,
            )
        )
        for event in prior:
            payload = event.payload or {}
            if event.kind == 'compact_progress' and payload.get('state') == 'done':
                return payload.get('summary') or None
            if event.kind == 'command' and payload.get('name') == '/compact':
                return payload.get('summary') or None
        return None

    def _pre_compact_hook(self) -> bool:
        """Return whether compaction should proceed (override hook)."""
        return True

    def _build_compact_inputs(self, prefix: list) -> list:
        """Build the summarization request inputs for a compaction."""
        budget = max(500, min(4000, self._resolve_context_window() // 200))
        prompt_parts = [COMPACT_SUMMARY_TEMPLATE, f'\nOutput ≤{budget} tokens.\n']
        if prior_summary := self._find_prior_compact_summary():
            prompt_parts.insert(
                0,
                (
                    f'<previous-summary>\n{prior_summary}\n</previous-summary>\n\n'
                    'Update the structure above: preserve still-true points, '
                    'drop stale ones, merge new info.\n\n'
                ),
            )
        prompt_text = ''.join(prompt_parts)
        return [
            {
                'role': 'system',
                'content': [{'type': 'input_text', 'text': COMPACT_SUMMARY_SYSTEM}],
            },
            *self._strip_internal_keys(prefix),
            {
                'role': 'user',
                'content': [{'type': 'input_text', 'text': prompt_text}],
            },
        ]

    def _estimate_conversation_tokens(self) -> int:
        """Roughly estimate the pending request size from the conversation."""
        return sum(
            self._estimate_entry_tokens(entry) for entry in (self.conversation or [])
        )

    def _maybe_auto_compact(self) -> bool:
        """Auto-compact when the pending request approaches the context window.

        Sizing uses the larger of the last reported input tokens and a fresh
        estimate of the current conversation, so a turn that has since appended
        large tool results is caught pre-flight instead of only reacting to the
        previous round's reported count.

        Compaction only summarizes the prefix and keeps the recent tail
        verbatim, so it is skipped when the tail alone already fills the ratio:
        summarizing then cannot bring the request under the window, and firing
        every iteration would only burn provider calls (e.g. a single pasted
        message larger than the window, which is always kept as the tail).
        """
        if self.state == 'compacting':
            return False
        window = self._resolve_context_window()
        if not window:
            return False
        pending = max(self.last_input_tokens or 0, self._estimate_conversation_tokens())
        if not pending or (pending / window) < COMPACT_AUTO_RATIO:
            return False
        if not (self.conversation or []):
            return False
        _prefix, tail = self._split_conversation_for_compact()
        tail_tokens = sum(self._estimate_entry_tokens(entry) for entry in tail)
        if (tail_tokens / window) >= COMPACT_AUTO_RATIO:
            return False
        resume_state = self.state if self.state == 'running' else None
        self._begin_compact_progress(auto=True)
        self.write({'state': 'compacting'})
        self._publish_event('state', {'state': 'compacting'})
        compact = (
            self.with_context(muk_ai_skip_done_notification=True)
            if resume_state
            else self
        )
        compact._do_compact(resume=True)
        if resume_state and self.state == 'done':
            self.write({'state': resume_state})
            self._publish_event('state', {'state': resume_state})
        return True

    def _begin_compact_progress(self, auto: bool = False) -> models.BaseModel:
        """Append and return a streaming compaction-progress event."""
        return self._append_event(
            {
                'kind': 'compact_progress',
                'name': '/compact',
                'auto': bool(auto),
                'state': 'streaming',
                'message_count': sum(
                    1
                    for item in (self.conversation or [])
                    if isinstance(item, dict)
                    and item.get('role') in ('user', 'assistant')
                ),
                'tokens_estimate': self.last_input_tokens or 0,
                'started_at': fields.Datetime.now().isoformat(),
                'streamed_text': '',
            }
        )

    def _find_active_compact_event(self) -> models.BaseModel:
        """Return the latest compaction-progress event for the session."""
        return (
            self.env['muk_ai.session.event']
            .sudo()
            .search(
                [
                    ('session_id', '=', self.id),
                    ('kind', '=', 'compact_progress'),
                ],
                order='sequence desc',
                limit=1,
            )
        )

    def _patch_compact_progress(self, event: models.BaseModel, patch: dict) -> None:
        """Merge a patch into a compaction-progress event and broadcast it."""
        if not event:
            return
        payload = dict(event.payload or {})
        payload.update(patch)
        event.payload = payload
        self._publish_event(
            'compact_update',
            {
                'event_id': event.id,
                'patch': patch,
            },
        )

    def _tail_drop_fallback(
        self,
        progress_event: models.BaseModel,
        prefix: list,
        tail: list,
        error: str | None,
        resume: bool = False,
    ) -> None:
        """Drop the oldest messages without a summary when compaction fails."""
        dropped = sum(
            1
            for item in prefix
            if isinstance(item, dict) and item.get('role') in ('user', 'assistant')
        )
        original_messages = sum(
            1
            for item in (self.conversation or [])
            if isinstance(item, dict) and item.get('role') in ('user', 'assistant')
        )
        original_tokens = self.last_input_tokens
        new_conversation = list(tail)
        self.write(
            {
                'conversation': new_conversation,
                'pending_ask': False,
                'error_message': False,
                'last_input_tokens': 0,
                'state': 'done',
                'cleared_at': fields.Datetime.now(),
            }
        )
        notice = _(
            'Compaction failed (%(error)s) — dropped %(dropped)s oldest '
            'message(s) without summary as a fallback.',
            error=error or 'unknown error',
            dropped=dropped,
        )
        self._patch_compact_progress(
            progress_event,
            {
                'state': 'done',
                'summary': notice,
                'streamed_text': notice,
                'original_messages': original_messages,
                'original_tokens': original_tokens,
                'fallback': 'tail_drop',
            },
        )
        self._publish_event('state', {'state': 'done'})
        if not resume and self.pending_ids:
            self._drain_pending_message()
            self._run_to_completion()

    def _do_compact(self, resume: bool = False) -> None:
        """Summarize the conversation prefix into a compact replacement."""
        if not self._pre_compact_hook():
            self.write({'state': 'done'})
            self._publish_event('state', {'state': 'done'})
            return
        progress_event = self._find_active_compact_event()
        if (
            not progress_event
            or (progress_event.payload or {}).get('state') != 'streaming'
        ):
            progress_event = self._begin_compact_progress(auto=False)
        prefix, tail = self._split_conversation_for_compact()
        if not prefix:
            self._patch_compact_progress(
                progress_event,
                {
                    'state': 'cancelled',
                    'message': _('Nothing to compact — conversation too short.'),
                },
            )
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
            self._coalesce_and_emit(
                stream_state,
                'buffer',
                'buffer_last',
                delta,
                'compact_delta',
                extra={'event_id': progress_event.id},
            )
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
        except Exception as error:  # noqa: BLE001 — fall back to tail-drop on any failure
            self._tail_drop_fallback(
                progress_event, prefix, tail, str(error), resume=resume
            )
            return
        if (progress_event.payload or {}).get('state') == 'cancelled':
            self.write({'state': 'done'})
            self._publish_event('state', {'state': 'done'})
            return
        self._accrue_usage(payload.get('usage') or {})
        summary = (payload.get('text') or stream_state['text'] or '').strip()
        if not summary:
            self._patch_compact_progress(
                progress_event,
                {
                    'state': 'cancelled',
                    'message': _('Compaction skipped: provider returned no summary.'),
                },
            )
            self.write({'state': 'done'})
            self._publish_event('state', {'state': 'done'})
            return
        original_messages = sum(
            1
            for item in (self.conversation or [])
            if isinstance(item, dict) and item.get('role') in ('user', 'assistant')
        )
        original_tokens = self.last_input_tokens
        new_conversation = [
            {
                'type': 'message',
                'role': 'assistant',
                'content': [
                    {
                        'type': 'output_text',
                        'text': f'{COMPACT_SUMMARY_REINJECTION}\n\n{summary}',
                    }
                ],
            },
            *tail,
        ]
        self.write(
            {
                'conversation': new_conversation,
                'pending_ask': False,
                'error_message': False,
                'last_input_tokens': 0,
                'state': 'done',
                'cleared_at': fields.Datetime.now(),
            }
        )
        self._patch_compact_progress(
            progress_event,
            {
                'state': 'done',
                'summary': summary,
                'streamed_text': summary,
                'original_messages': original_messages,
                'original_tokens': original_tokens,
            },
        )
        self._publish_event('state', {'state': 'done'})
        if not resume and self.pending_ids:
            self._drain_pending_message()
            self._run_to_completion()

    # ----------------------------------------------------------
    # Helper History
    # ----------------------------------------------------------

    def _resolve_event(self, event_id: int) -> models.BaseModel:
        """Return a session event by id, or raise when missing.

        :raise UserError: when the event is not part of this session
        """
        self.ensure_one()
        event = (
            self.env['muk_ai.session.event']
            .sudo()
            .search(
                [
                    ('session_id', '=', self.id),
                    ('id', '=', int(event_id)),
                ],
                limit=1,
            )
        )
        if not event:
            raise UserError(_('Event not found in this session.'))
        return event

    @staticmethod
    def _is_counted_user_entry(item) -> bool:
        """Return whether the item is a user entry backed by a user_message event.

        Answer-carried entries (``_answer_entry``) and tool-produced vision
        entries (``_vision_entry``) have no ``user_message`` event, so they must
        not shift the positional mapping between events and user conversation
        items.
        """
        return (
            isinstance(item, dict)
            and item.get('role') == 'user'
            and not item.get('_answer_entry')
            and not item.get('_vision_entry')
        )

    def _conversation_cut_index(self, event: models.BaseModel) -> int:
        """Return the conversation index to cut at when undoing to an event."""
        earlier_user_msgs = (
            self.env['muk_ai.session.event']
            .sudo()
            .search_count(
                [
                    ('session_id', '=', self.id),
                    ('sequence', '<', event.sequence),
                    ('kind', '=', 'user_message'),
                ]
            )
        )
        conv = list(self.conversation or [])
        user_seen = 0
        if event.kind == 'user_message':
            for i, item in enumerate(conv):
                if self._is_counted_user_entry(item):
                    if user_seen == earlier_user_msgs:
                        return i
                    user_seen += 1
            return len(conv)
        for i, item in enumerate(conv):
            if self._is_counted_user_entry(item):
                user_seen += 1
                if user_seen == earlier_user_msgs:
                    return i + 1
        return len(conv)

    def _conversation_cut_index_for_fork(self, event: models.BaseModel) -> int:
        """Return the conversation index to cut at when forking at an event."""
        earlier_user_msgs = (
            self.env['muk_ai.session.event']
            .sudo()
            .search_count(
                [
                    ('session_id', '=', self.id),
                    ('sequence', '<', event.sequence),
                    ('kind', '=', 'user_message'),
                ]
            )
        )
        conv = list(self.conversation or [])
        user_seen = 0
        if event.kind == 'user_message':
            for i, item in enumerate(conv):
                if self._is_counted_user_entry(item):
                    if user_seen == earlier_user_msgs:
                        return i + 1
                    user_seen += 1
            return len(conv)
        for i, item in enumerate(conv):
            if self._is_counted_user_entry(item):
                user_seen += 1
                if user_seen > earlier_user_msgs:
                    return i
        return len(conv)

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    def fetch_events(
        self, limit: int = 100, before_sequence: int | None = None
    ) -> dict:
        """Return a window of session events with older-page metadata."""
        if self.id:
            self.check_access_rights('read')
            self.check_access_rule('read')
            domain = [('session_id', '=', self.id)]
            if before_sequence is not None:
                domain.append(('sequence', '<', before_sequence))
            rows = (
                self.env['muk_ai.session.event']
                .sudo()
                .search(
                    domain,
                    order='sequence desc, id desc',
                    limit=limit + 1,
                )
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

    def get_snapshot(self, include_conversation: bool = False) -> dict:
        """Return a client snapshot of the session state and recent events."""
        events_window = self.fetch_events(limit=100)
        snapshot = {
            'id': self.id,
            'events': events_window['events'],
            'has_more_older': events_window['has_more_older'],
            'oldest_sequence': events_window['oldest_sequence'],
            'error_message': self.error_message,
            'last_text': self.last_text,
            'attachments': [a._ai_describe() for a in self.attachment_ids],
            'total_input_cost': self.total_input_cost,
            'total_output_cost': self.total_output_cost,
            'pending_user_messages': self._serialize_pending(),
            **self._state_metrics(),
        }
        if include_conversation:
            snapshot['conversation'] = self.conversation or []
        return snapshot

    def dismiss_notifications(self) -> bool:
        """Clear the attention flag and mark inbox notifications read."""
        if partner := self.env.user.partner_id:
            messages = (
                self.env['mail.message']
                .sudo()
                .search(
                    [
                        ('muk_ai_session_id', 'in', self.ids),
                        ('notification_ids.res_partner_id', '=', partner.id),
                        ('notification_ids.is_read', '=', False),
                    ]
                )
            )
            if messages:
                messages.with_user(self.env.user).set_message_done()
            self.filtered('notification_unread').notification_unread = False
            self._push_notification_badge(self.env.user)
            return True
        return False

    @api.model
    def _notification_unread_session_ids(self, user: models.BaseModel) -> list:
        """Return the ids of the user's sessions awaiting attention."""
        if not user:
            return []
        return (
            self.sudo()
            .search(
                [
                    ('user_id', '=', user.id),
                    ('notification_unread', '=', True),
                ]
            )
            .ids
        )

    @api.model
    def _notification_badge_payload(self, user: models.BaseModel) -> dict:
        """Return the badge count and unread session ids for a user."""
        ids = self._notification_unread_session_ids(user)
        return {'count': len(ids), 'session_ids': ids}

    @api.model
    def notification_badge(self) -> dict:
        """Return the attention badge payload for the current user."""
        return self._notification_badge_payload(self.env.user)

    def _push_notification_badge(self, user: models.BaseModel) -> None:
        """Push the attention badge payload to the user's systray."""
        if not user or not user.partner_id:
            return
        with suppress(Exception):
            self.env['bus.bus']._sendone(
                user.partner_id,
                'muk_ai.notification_badge',
                self._notification_badge_payload(user),
            )

    def start(
        self,
        user_message: str | None = None,
        attachment_ids: list[int] | None = None,
    ) -> dict:
        """Start a session turn and trigger a worker.

        :raise UserError: when the session is not in a startable state
        """
        self._recover_if_stuck()
        if self.state not in ('new', 'error', 'stopped'):
            raise UserError(_('Session is not in a startable state.'))
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

    def answer(self, answer: str, attachment_ids: list[int] | None = None) -> dict:
        """Answer a pending question and resume the turn.

        :raise UserError: when the session is not awaiting an answer
        """
        self._recover_if_stuck()
        pending = self.pending_ask or {}
        if self.state != 'waiting' or pending.get('kind') != 'question':
            raise UserError(_('Session is not waiting for user input.'))
        question = pending.get('text') or ''
        attachments = self._resolve_attachments(attachment_ids)
        continuation = []
        if call_id := pending.get('call_id'):
            continuation.append(
                build_tool_call_output(
                    call_id,
                    {'status': 'answered', 'question': question, 'answer': answer},
                )
            )
            if attachments and (entry := self._build_user_entry(None, attachments)):
                continuation.append({**entry, '_answer_entry': True})
        else:
            followup_text = f'Answer to "{question}": {answer}' if question else answer
            if user_entry := self._build_user_entry(followup_text, attachments):
                continuation.append({**user_entry, '_answer_entry': True})
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
        self._recover_if_stuck()
        if self.state in ('running', 'compacting'):
            return self.enqueue_message(user_message, attachment_ids=attachment_ids)
        if self.state == 'waiting':
            kind = (self.pending_ask or {}).get('kind')
            if kind in ('approval', 'client_action'):
                return self.enqueue_message(user_message, attachment_ids=attachment_ids)
            if kind == 'question':
                return self.answer(user_message, attachment_ids=attachment_ids)
        if not self.conversation:
            return self.start(user_message, attachment_ids=attachment_ids)
        attachments = self._resolve_attachments(attachment_ids)
        self._enqueue_user_turn(user_message, attachments)
        self._trigger_worker()
        return self.get_snapshot()

    def regenerate_last_turn(self) -> dict:
        """Rewind to the last user turn and re-run it.

        :raise UserError: when running, compacting, waiting, or no user turn exists
        """
        if self.state in ('running', 'compacting', 'waiting'):
            raise UserError(
                _(
                    'Cannot regenerate while the session is running, compacting, or waiting.'
                )
            )
        conv = list(self.conversation or [])
        last_user = next(
            (
                idx
                for idx in range(len(conv) - 1, -1, -1)
                if self._is_counted_user_entry(conv[idx])
            ),
            None,
        )
        if last_user is None:
            raise UserError(_('No user turn to regenerate from.'))
        self.conversation = conv[: last_user + 1]
        Event = self.env['muk_ai.session.event'].sudo()
        last_user_event = Event.search(
            [('session_id', '=', self.id), ('kind', '=', 'user_message')],
            order='sequence desc, id desc',
            limit=1,
        )
        if last_user_event:
            stale = Event.search(
                [
                    ('session_id', '=', self.id),
                    '|',
                    ('sequence', '>', last_user_event.sequence),
                    '&',
                    ('sequence', '=', last_user_event.sequence),
                    ('id', '>', last_user_event.id),
                ]
            )
        else:
            stale = Event.search([('session_id', '=', self.id)])
        if stale:
            stale.unlink()
        self.write(
            {
                'pending_ask': False,
                'error_message': False,
                'state': 'running',
                'claimed_at': False,
                'turn_wallclock_spent': 0.0,
                'turn_cost_spent': 0.0,
            }
        )
        self._publish_event('state', {'state': 'running'})
        self._trigger_worker()
        return self.get_snapshot()

    def clear(self) -> dict:
        """Reset the conversation and session state to new.

        :raise UserError: when the session is running or compacting
        """
        if self.state in ('running', 'compacting'):
            raise UserError(
                _('Cannot clear the conversation while the session is running.')
            )
        if self.pending_ids:
            self.pending_ids.unlink()
            self.invalidate_recordset(['pending_ids'])
        self.write(
            {
                'conversation': [],
                'pending_ask': False,
                'approved_signatures': [],
                'last_text': False,
                'error_message': False,
                'iteration_count': 0,
                'last_input_tokens': 0,
                'state': 'new',
                'cleared_at': fields.Datetime.now(),
            }
        )
        self._append_event(
            {
                'kind': 'command',
                'name': '/clear',
                'message': _('Context cleared.'),
            }
        )
        self._publish_event('state', {'state': 'new'})
        self._publish_event('queue', {'pending': []})
        return self.get_snapshot()

    def compact(self) -> dict:
        """Begin asynchronous conversation compaction.

        :raise UserError: when running, waiting, or the conversation is empty
        """
        if self.state in ('running', 'compacting'):
            raise UserError(
                _('Cannot compact while the session is running. Stop first.')
            )
        if self.state == 'waiting':
            raise UserError(
                _('Cannot compact while the session is waiting for user input.')
            )
        if not self.conversation:
            raise UserError(_('Nothing to compact yet — the conversation is empty.'))
        self._begin_compact_progress(auto=False)
        self.write({'state': 'compacting', 'error_message': False})
        self._publish_event('state', {'state': 'compacting'})
        self._trigger_worker()
        return self.get_snapshot()

    def stop_compact(self) -> dict:
        """Cancel an in-progress compaction and return to done."""
        if self.state != 'compacting':
            return self.get_snapshot()
        event = self._find_active_compact_event()
        if event and (event.payload or {}).get('state') == 'streaming':
            self._patch_compact_progress(
                event,
                {
                    'state': 'cancelled',
                    'message': _('Compaction cancelled by user.'),
                },
            )
        self.write({'state': 'done', 'error_message': False})
        self._publish_event('state', {'state': 'done'})
        return self.get_snapshot()

    def undo_to_event(self, event_id: int) -> dict:
        """Rewind the conversation and events back to before an event.

        :raise UserError: when the session is running, compacting, or waiting
        """
        if self.state in ('running', 'compacting'):
            raise UserError(_('Cannot rewind while the session is running.'))
        if self.state == 'waiting':
            raise UserError(_('Cannot rewind while the session is waiting for input.'))
        target = self._resolve_event(event_id)
        cut_index = self._conversation_cut_index(target)
        stale = (
            self.env['muk_ai.session.event']
            .sudo()
            .search(
                [
                    ('session_id', '=', self.id),
                    ('sequence', '>=', target.sequence),
                ]
            )
        )
        if stale:
            stale.unlink()
        new_conv = list(self.conversation or [])[:cut_index]
        self.write(
            {
                'conversation': new_conv,
                'pending_ask': False,
                'last_text': False,
                'error_message': False,
                'state': 'done' if new_conv else 'new',
            }
        )
        self._publish_event('state', {'state': self.state})
        return self.get_snapshot()

    def fork_at_event(self, event_id: int) -> int:
        """Fork a new session copied up to the given event; return its id.

        :raise UserError: when the session is running or compacting
        """
        if self.state in ('running', 'compacting'):
            raise UserError(_('Cannot fork while the session is running.'))
        target = self._resolve_event(event_id)
        cut_index = self._conversation_cut_index_for_fork(target)
        new_conv = list(self.conversation or [])[:cut_index]
        fork = self.copy(
            {
                'name': _('%s (fork)', self.name),
                'conversation': new_conv,
                'state': 'done' if new_conv else 'new',
                'pending_ask': False,
                'last_text': False,
                'error_message': False,
                'iteration_count': 0,
                'event_ids': [(5, 0, 0)],
                'pending_ids': [(5, 0, 0)],
            }
        )
        source_events = (
            self.env['muk_ai.session.event']
            .sudo()
            .search(
                [
                    ('session_id', '=', self.id),
                    ('sequence', '<=', target.sequence),
                ],
                order='sequence, id',
            )
        )
        if source_events:
            self.env['muk_ai.session.event'].sudo().create(
                [
                    {
                        'session_id': fork.id,
                        'sequence': src.sequence,
                        'kind': src.kind,
                        'payload': src.payload,
                        'at': src.at,
                    }
                    for src in source_events
                ]
            )
        return fork.id

    def upload_attachments(self, files: list[dict] | None) -> list[dict]:
        """Create session attachments from uploads and return descriptors."""
        self.check_access_rights('write')
        self.check_access_rule('write')
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
            self.invalidate_recordset(['attachment_ids'])
        return [a._ai_describe() for a in created]

    def discard_attachments(self, attachment_ids: list[int] | None) -> bool:
        """Unlink the named attachments owned by this session."""
        self.check_access_rights('write')
        self.check_access_rule('write')
        if attachment_ids:
            ids = {int(aid) for aid in attachment_ids}
            owned = self.attachment_ids.filtered(lambda a: a.id in ids)
            if owned:
                owned.sudo().unlink()
                self.invalidate_recordset(['attachment_ids'])
        return True

    def set_view_context(self, payload: dict | None) -> dict:
        """Pin or clear the session's view context from a client payload."""
        kind = payload.get('kind') if isinstance(payload, dict) else None
        self._write_view_context(
            None
            if payload is None or kind == 'none'
            else clean_view_context_payload(kind, payload)
        )
        return self.get_snapshot()

    def unpin_view_context(self) -> dict:
        """Clear the pinned view context and record the command."""
        self._write_view_context(None)
        self._append_event(
            {
                'kind': 'command',
                'name': '/unpin',
                'message': _('View context cleared.'),
            }
        )
        return self.get_snapshot()

    def set_approval_mode(self, mode: str | None) -> dict:
        """Override the session approval mode.

        :raise UserError: when the mode is not ``ask`` or ``off``
        """
        if mode and mode not in ('ask', 'off'):
            raise UserError(_('Unknown approval mode %(mode)r.', mode=mode))
        self.write({'override_approval_mode': mode or False})
        self._publish_event('state', {'state': self.state})
        return self.get_snapshot()

    def approve_tool(self) -> dict:
        """Approve the pending tool call once and resume the round."""
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

    def approve_for_session(self) -> dict:
        """Approve the pending call and whitelist its signature for the session."""
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

    def reject_tool(self, reason: str | None = None) -> dict:
        """Reject the pending tool call and resume the round with the rejection."""
        pending = self._require_pending_approval()
        reason = (reason or '').strip() or _('User rejected the call.')
        self._record_approval_audit(
            decision='rejected',
            call={
                'name': pending.get('name'),
                'arguments': pending.get('arguments'),
            },
            risk=pending.get('risk') or {},
            reject_reason=reason,
        )
        self._resume_tool_round(pending, approved=False, reject_reason=reason)
        if self.state == 'running':
            self._trigger_worker()
        return self.get_snapshot()

    def submit_client_result(self, call_id: str, result) -> dict:
        """Submit a client-executed tool result, resuming once all are in.

        :raise UserError: when the session is busy or not awaiting this
            client action
        """
        if not self._try_session_lock(self.id):
            raise UserError(_('The session is currently busy. Please try again.'))
        try:
            pending = self._require_pending_client_action(call_id)
            self._apply_client_result(pending, call_id, result)
        finally:
            self._release_session_lock(self.id)
        return self.get_snapshot()

    def reject_client_action(
        self, call_id: str | None = None, reason: str | None = None
    ) -> dict:
        """Reject one or all pending client actions with an error result.

        Without ``call_id`` every unanswered action in the batch is
        rejected, which always resumes the turn.

        :raise UserError: when the session is busy or not awaiting this
            client action
        """
        if not self._try_session_lock(self.id):
            raise UserError(_('The session is currently busy. Please try again.'))
        try:
            pending = self._require_pending_client_action(call_id)
            result = {'error': 'rejected', 'reason': reason or ''}
            if call_id is not None:
                self._apply_client_result(pending, call_id, result)
                return self.get_snapshot()
            results = pending.get('results') or {}
            for action in pending.get('actions') or []:
                if action.get('call_id') in results:
                    continue
                self._apply_client_result(pending, action['call_id'], result)
            return self.get_snapshot()
        finally:
            self._release_session_lock(self.id)

    # ----------------------------------------------------------
    # Actions
    # ----------------------------------------------------------

    def action_open(self) -> dict:
        """Return the client action that opens this chat session.

        :raise AccessError: when the caller is not the session owner
        """
        self.ensure_one()
        if self.user_id.id != self.env.uid:
            raise AccessError(_('Only the session owner can continue this chat.'))
        return {
            'type': 'ir.actions.client',
            'tag': 'muk_ai.chat',
            'name': self.name or _('AI Chat'),
            'params': {'session_id': self.id},
        }

    def action_stop(self) -> dict:
        """Stop the session, flushing any pending tool outputs.

        :raise AccessError: when the caller is not the owner or an admin
        """
        self.ensure_one()
        if self.user_id.id != self.env.uid and not self.env.is_admin():
            raise AccessError(
                _('Only the session owner or an administrator can stop this session.')
            )
        if self.state not in ('done', 'error', 'stopped'):
            if self.state == 'waiting':
                self._flush_orphaned_tool_outputs()
            self.write({'state': 'stopped', 'pending_ask': False})
            self._publish_event('state', {'state': 'stopped'})
        return self.get_snapshot()

    def action_handover(self, new_user_id: int) -> bool:
        """Transfer ownership of this session to another internal user.

        :param new_user_id: the target ``res.users`` id
        :raise AccessError: when the caller is not the owner or an admin
        :raise UserError: when the session is busy or the target is invalid
        """
        self.ensure_one()
        if self.user_id.id != self.env.uid and not self.env.is_admin():
            raise AccessError(
                _('Only the session owner or an administrator can hand over this chat.')
            )
        if self.state in ('running', 'compacting'):
            raise UserError(_('Stop the session before handing it over.'))
        target = self.env['res.users'].sudo().browse(new_user_id).exists()
        if not target or target.share or not target.active:
            raise UserError(_('Select an active internal user to hand over to.'))
        if target.id == self.user_id.id:
            return True
        old_owner, session = self.user_id, self.sudo()
        session.write({'user_id': target.id, 'notification_unread': True})
        session._publish_event('state', {'state': session.state})
        session._post_inbox_notification(
            _('Chat handed over to you'),
            _(
                '%(name)s handed you the chat "%(chat)s".',
                name=old_owner.name,
                chat=session.name or '',
            ),
        )
        session._push_notification_badge(target)
        session._push_notification_badge(old_owner)
        return True

    # ----------------------------------------------------------
    # Compute
    # ----------------------------------------------------------

    @api.depends('agent_id', 'agent_id.model_id', 'agent_id.model_id.context_window')
    def _compute_context_window(self) -> None:
        """Resolve the effective context window for each session."""
        for record in self:
            record.context_window = record._resolve_context_window()

    @api.depends('override_approval_mode', 'agent_id', 'agent_id.approval_mode')
    def _compute_effective_approval_mode(self) -> None:
        """Resolve the effective approval mode for each session."""
        for record in self:
            record.effective_approval_mode = record._effective_approval_mode()

    @api.depends(
        'pending_ids',
        'pending_ids.queued_at',
        'pending_ids.content',
        'pending_ids.attachment_ids',
    )
    def _compute_pending_user_messages(self) -> None:
        """Serialize the queued pending messages for the client."""
        for record in self:
            record.pending_user_messages = record._serialize_pending()

    @api.depends('event_ids', 'event_ids.sequence', 'event_ids.payload')
    def _compute_display_events(self) -> None:
        """Load the most recent events for display."""
        for record in self:
            record.display_events = (
                record.fetch_events(limit=100)['events'] if record.id else []
            )

    # ----------------------------------------------------------
    # ORM
    # ----------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list: list[dict]) -> AISession:
        """Enforce the rate limit and broadcast initial state on create."""
        self._check_rate_limit(batch_size=len(vals_list) or 1)
        records = super().create(vals_list)
        for record in records:
            with suppress(Exception):
                record._bus_send(
                    'muk_ai.session_state',
                    {
                        'session_id': record.id,
                        'name': record.name,
                        'state': record.state,
                    },
                )
        return records

    def write(self, vals: dict) -> bool:
        """Emit an in-transcript marker whenever the active agent changes.

        Captures the previous agent per record, then for every session whose
        ``agent_id`` actually changes emits a persisted ``agent_switched`` event
        (rendered as a divider) plus the live pill update. As the single ORM
        chokepoint it covers the UI dropdown, the ``/agent`` command and the
        ``switch_agent`` MCP tool with one consistent marker.
        """
        if 'agent_id' not in vals:
            return super().write(vals)
        previous = {record.id: record.agent_id for record in self}
        result = super().write(vals)
        for record in self:
            if (old_agent := previous.get(record.id)) != record.agent_id:
                record._append_event(
                    {
                        'kind': 'agent_switched',
                        'agent_name': record.agent_id.name if record.agent_id else '',
                        'from_agent_name': old_agent.name if old_agent else '',
                    }
                )
                record._publish_event(
                    'agent_switched',
                    {
                        'agent_id': record.agent_id.id if record.agent_id else False,
                        'agent_name': record.agent_id.name if record.agent_id else '',
                        'effective_approval_mode': record._effective_approval_mode(),
                    },
                )
        return result

    def unlink(self) -> bool:
        """Broadcast deletions so open chat surfaces drop the session live."""
        users = self.user_id
        for record in self:
            with suppress(Exception):
                record._bus_send(
                    'muk_ai.session_state',
                    {'session_id': record.id, 'deleted': True},
                )
        result = super().unlink()
        for session_user in users:
            with suppress(Exception):
                self._push_notification_badge(session_user)
        return result

    # ----------------------------------------------------------
    # Cron
    # ----------------------------------------------------------

    @api.model
    def _client_action_timeout(self) -> int:
        """Return the stale client-action timeout in seconds (0 disables)."""
        raw = (
            self.env['ir.config_parameter']
            .sudo()
            .get_param('muk_ai.client_action_timeout', CLIENT_ACTION_TIMEOUT_SECONDS)
        )
        try:
            return int(raw)
        except (TypeError, ValueError):
            return CLIENT_ACTION_TIMEOUT_SECONDS

    @api.model
    def _sweep_stale_client_actions(self) -> None:
        """Auto-reject client-action batches whose client never responded."""
        timeout = self._client_action_timeout()
        if timeout <= 0:
            return
        threshold = fields.Datetime.now() - timedelta(seconds=timeout)
        for session in self.sudo().search([('state', '=', 'waiting')]):
            pending = session.pending_ask or {}
            if pending.get('kind') != 'client_action':
                continue
            registered = fields.Datetime.to_datetime(pending.get('registered_at') or '')
            if not registered or registered > threshold:
                continue
            with suppress(UserError):
                session.reject_client_action(
                    reason='timeout: the client did not respond'
                )

    @api.model
    def _cron_run_pending_sessions(self) -> None:
        """Sweep orphans and process pending sessions in this worker slot."""
        candidates = self._find_pending_session_ids()
        self._sweep_orphan_sessions(skip_ids=candidates)
        self._sweep_stale_client_actions()
        if candidates:
            self._commit_safe()
            for sid in candidates:
                if self._process_session_in_worker(sid):
                    break
            if len(candidates) > 1:
                self._trigger_worker()

    @api.model
    def _sweep_orphan_sessions(self, skip_ids: list[int] | None = None) -> None:
        """Mark abandoned running or compacting sessions as errored."""
        threshold = fields.Datetime.now() - timedelta(seconds=WORKER_STALE_THRESHOLD)
        candidates = self.sudo().search(
            [
                ('id', 'not in', skip_ids or []),
                ('state', 'in', ('running', 'compacting')),
                ('write_date', '<', threshold),
                '|',
                ('claimed_at', '=', False),
                ('claimed_at', '<', threshold),
            ]
        )
        for session in candidates:
            if not self._try_session_xact_lock(session.id):
                continue
            try:
                with self.env.cr.savepoint():
                    session._close_orphan_tool_calls('worker abandoned the session')
                    session.write(
                        {
                            'state': 'error',
                            'error_message': _(
                                'Worker abandoned the session — please retry.'
                            ),
                        }
                    )
                session._publish_event(
                    'state',
                    {
                        'state': 'error',
                        'error': session.error_message,
                    },
                )
            except psycopg2.errors.SerializationFailure:
                continue

    @api.model
    def _session_worker_crons(self) -> models.BaseModel:
        """Return the active AI-session worker cron records."""
        return (
            self.env['ir.cron']
            .sudo()
            .search(
                [
                    ('state', '=', 'ai_session'),
                    ('active', '=', True),
                ]
            )
        )

    @api.model
    def _active_worker_count(self) -> int:
        """Return the number of active worker crons, at least one."""
        return max(1, len(self._session_worker_crons()))

    @api.model
    def _find_pending_session_ids(self, limit: int | None = None) -> list[int]:
        """Return ids of pending sessions, oldest first, up to a limit."""
        if limit is None:
            limit = self._active_worker_count()
        self.env.cr.execute(
            SQL(
                """
            SELECT id FROM muk_ai_session
            WHERE state IN ('running', 'compacting')
            ORDER BY write_date
            LIMIT %s
            """,
                limit,
            )
        )
        return [row[0] for row in self.env.cr.fetchall()]

    @api.model
    def _dispatch_queued_turns(self, session_ids: tuple[int, ...]) -> None:
        """Run queued turns in order while the worker budget still allows it.

        :param session_ids: sessions to process, in queue order
        """
        for session_id in session_ids:
            remaining = self._worker_hard_limit_seconds()
            if (
                remaining
                and remaining < WALLCLOCK_MIN_SECONDS + WALLCLOCK_SAFETY_MARGIN
            ):
                break
            self._process_session_in_worker(session_id)

    @api.model
    def _process_session_in_worker(self, session_id: int) -> bool:
        """Process one session under an advisory lock in a fresh cursor."""
        processed = False
        with self.pool.cursor() as cr:
            cr.execute(
                SQL(
                    'SELECT pg_try_advisory_lock(%s, %s)',
                    ADVISORY_LOCK_NAMESPACE,
                    session_id,
                )
            )
            if cr.fetchone()[0]:
                try:
                    env_su = api.Environment(cr, SUPERUSER_ID, {})
                    session_su = env_su['muk_ai.session'].browse(session_id)
                    if session_su.exists() and session_su.state in (
                        'running',
                        'compacting',
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
                        except Exception as error:  # noqa: BLE001 — record any worker failure
                            cr.rollback()
                            self._mark_session_error(session_id, str(error))
                        processed = True
                finally:
                    with suppress(Exception):
                        cr.execute(
                            SQL(
                                'SELECT pg_advisory_unlock(%s, %s)',
                                ADVISORY_LOCK_NAMESPACE,
                                session_id,
                            )
                        )
                        cr.fetchone()
        return processed

    @api.model
    def _mark_session_error(self, session_id: int, message: str) -> None:
        """Mark a session errored in its own cursor and notify the client."""
        with self.pool.cursor() as cr:
            session = api.Environment(cr, SUPERUSER_ID, {})['muk_ai.session'].browse(
                session_id
            )
            if session.exists():
                session._close_orphan_tool_calls(message)
                session.write(
                    {
                        'state': 'error',
                        'error_message': message,
                    }
                )
                session._publish_event(
                    'state',
                    {
                        'state': 'error',
                        'error': message,
                    },
                )
                cr.commit()

    def _capture_user_context(self) -> dict:
        """Return the JSON-serializable subset of the current context."""
        safe = {}
        for key, value in (self.env.context or {}).items():
            try:
                json.dumps(value)
            except (TypeError, ValueError):
                continue
            safe[key] = value
        return safe

    @api.model
    def _dispatch_inline(self) -> bool:
        """Return whether a queued turn may run in the current request.

        Cron dispatch is only prompt when a worker is woken by the trigger
        notification, which a pooled connection swallows, so the request
        path is preferred wherever it cannot block a scarce worker.
        """
        if modules.module.current_test or config['workers']:
            return False
        mode = self.env['ir.config_parameter'].sudo().get_param('muk_ai.dispatch_mode')
        if mode in ('inline', 'cron'):
            return mode == 'inline'
        return True

    def _trigger_worker(self) -> None:
        """Persist the user context and dispatch the turn to a worker."""
        self.sudo().write(
            {
                'user_context': self._capture_user_context(),
            }
        )
        if modules.module.current_test:
            for session in self:
                if session.state == 'compacting':
                    session._do_compact()
                elif session.state == 'running':
                    session._run_to_completion()
            return
        if crons := self._session_worker_crons():
            random.choice(crons)._trigger()
        if request and self._dispatch_inline():
            queued = getattr(request, 'muk_ai_dispatch_ids', ())
            request.muk_ai_dispatch_ids = tuple(dict.fromkeys(queued + tuple(self.ids)))
