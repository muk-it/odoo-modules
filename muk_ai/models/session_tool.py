from __future__ import annotations

import base64
import contextlib
import json
from collections.abc import Container

import urllib3

from odoo import fields, models
from odoo.exceptions import ConcurrencyError, UserError
from odoo.sql_db import PG_CONCURRENCY_EXCEPTIONS_TO_RETRY
from odoo.tools import config

from odoo.addons.muk_ai.tools.attachment import (
    ALLOWED_MIMETYPES,
    ATTACHMENT_REF_MAX_BYTES,
    ATTACHMENT_REF_RE,
    IMAGE_MIMETYPES,
    TOOL_VISION_MAX_B64_CHARS,
    TOOL_VISION_MAX_IMAGES,
    URL_REF_RE,
    tool_file_payload,
)
from odoo.addons.muk_ai.tools.call import (
    TOOL_LOAD_TOOL,
    build_tool_call_output,
    clean_ask_preview,
)
from odoo.addons.muk_ai.tools.conversation import order_outputs
from odoo.addons.muk_ai.tools.runtime import MAX_TOOL_CALLS_PER_ROUND
from odoo.addons.muk_ai.tools.sources import extract_sources
from odoo.addons.muk_ai.tools.url_fetch import fetch_url
from odoo.addons.muk_ai.tools.vision import (
    image_specs,
    note_vision_unavailable,
    strip_images,
)
from odoo.addons.muk_mcp.core.tool import get_tool_index

PRIVATE_ASK_KEYS = (
    'arguments',
    'tool_calls',
    'outputs',
    'resume_index',
    'has_terminating',
    'results',
)

SKIP_REASONS = {
    'ask_user': 'skipped: ask_user pending, call again after user answer',
    'client': 'skipped: client action pending, call again after the client responds',
    'terminating': 'skipped: terminating tool already ran; emit a short summary and stop',
}


class AISessionTool(models.AbstractModel):
    """Tool rounds of a chat: dispatch, approvals, client actions and results."""

    _name = 'muk_ai.session.tool'
    _description = 'AI Session Tools'
    _explanation = (
        'The part of a chat that runs the tools the model calls, pauses for '
        'approvals, questions and client actions, and records the results.'
    )

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    pending_ask = fields.Json(
        string='Pending Ask',
        readonly=True,
        copy=False,
    )

    approved_signatures = fields.Json(
        string='Approved Signatures',
        readonly=True,
    )

    deferred_vision_attachment_ids = fields.Json(
        string='Deferred Vision Attachments',
        readonly=True,
    )

    disabled_tool_sources = fields.Json(
        string='Switched Off Tools',
        help='Keys of the tool sources switched off for this chat.',
        readonly=True,
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _tool_source_enabled(self, key: str) -> bool:
        """Return whether the tool source ``key`` is switched on for this chat."""
        return key not in (self.disabled_tool_sources or [])

    def _tool_sources(self) -> list[dict]:
        """Return the tool sources a user can switch off for this chat.

        A source is ``{key, section, icon, label, hint, enabled}``, a connector also
        lists its ``items``; the abilities listed are those the agent has.
        """
        agent = self.agent_id
        abilities = [
            (
                'web_search',
                'explore',
                self.env._('Web search'),
                self.env._('Search the web for current information'),
                agent._web_search_route(),
            ),
            (
                'image_generation',
                'image',
                self.env._('Images'),
                self.env._('Create images from a description'),
                agent._resolve_model_for('image'),
            ),
            (
                'code_interpreter',
                'terminal',
                self.env._('Code interpreter'),
                self.env._('Run code to calculate and analyse data'),
                agent._code_interpreter_route(),
            ),
        ]
        section = self.env._('Abilities')
        return [
            {
                'key': key,
                'section': section,
                'icon': icon,
                'label': label,
                'hint': hint,
                'enabled': self._tool_source_enabled(key),
            }
            for key, icon, label, hint, available in abilities
            if available
        ]

    def _tool_dispatch_context(self) -> dict:
        """Return the context keys threaded through tool dispatch."""
        return {'muk_mcp_session_id': self.id}

    def _enforce_tool_scope(self) -> str | None:
        """Return the MCP scope tool calls are capped at, or ``None`` for all.

        Extension modules narrow this per session: a session started from an
        untrusted surface stays read-only whatever its agent is allowed to do.
        """
        return 'read' if self.agent_id.read_only else None

    def _can_ask_user(self) -> bool:
        """Return whether this session may stop and put a question to a human.

        Extension modules answer ``False`` for a session nobody is watching; the
        dispatcher refuses a call the model emits anyway.
        """
        return True

    def _pending_ask_queues_input(self, pending: dict | None = None) -> bool:
        """Tell whether typed input queues behind the pending ask."""
        pending = self.pending_ask if pending is None else pending
        return (pending or {}).get('kind') in ('approval', 'client_action')

    def _public_pending_ask(self, pending: dict | None = None) -> dict | None:
        """Return the pending ask payload stripped of internal keys."""
        pending = self.pending_ask if pending is None else pending
        if not pending:
            return None
        public = {
            key: value for key, value in pending.items() if key not in PRIVATE_ASK_KEYS
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
        public['queues_input'] = self._pending_ask_queues_input(pending)
        return public

    def _resolve_value_refs(self, arguments: dict) -> tuple[dict, list[str]]:
        """Inline the attachment and URL references found in tool arguments.

        :return: the resolved arguments and the preview URL of each reference
        """
        previews = []

        def resolve(value) -> object:
            """Return the value with every reference it holds inlined as base64."""
            if isinstance(value, dict):
                return {key: resolve(item) for key, item in value.items()}
            if isinstance(value, list):
                return [resolve(item) for item in value]
            if not isinstance(value, str):
                return value
            if match := ATTACHMENT_REF_RE.match(value):
                attachment = self.env['ir.attachment'].browse(int(match.group(1)))
                attachment = attachment.exists()
                if not attachment or not attachment.has_access('read'):
                    return value
                attachment = attachment.sudo()
                if (
                    attachment.raw
                    and attachment.file_size <= ATTACHMENT_REF_MAX_BYTES
                    and (
                        not attachment.mimetype
                        or attachment.mimetype in ALLOWED_MIMETYPES
                    )
                ):
                    previews.append(f'/web/image/{attachment.id}')
                    return attachment.raw.to_base64()
            elif match := URL_REF_RE.match(value):
                try:
                    result = fetch_url(match.group(1))
                except (UserError, urllib3.exceptions.HTTPError):
                    return value
                previews.append(match.group(1))
                return base64.b64encode(result.body).decode()
            return value

        return resolve(arguments), previews

    def _dispatch_tool_call(self, name: str, arguments: dict, call_id: str) -> tuple:
        """Execute a tool call and return its output and success flag.

        The chat's own context keys win over those of the tool arguments.
        """
        if name == TOOL_LOAD_TOOL['name']:
            output = self._dispatch_tool_load(arguments, call_id)
            return output, 'error' not in output
        arguments, previews = self._resolve_value_refs(arguments)
        bound = self._tool_dispatch_context()
        if isinstance(arguments, dict) and isinstance(
            context := arguments.get('context'), dict
        ):
            arguments = {
                **arguments,
                'context': {k: v for k, v in context.items() if k not in bound},
            }
        try:
            tool_env = self.env(context={**self.env.context, **bound})
            text, _info = tool_env['muk_mcp.tool']._call(
                name, arguments, tool_env, enforce_scope=self._enforce_tool_scope()
            )
        except (*PG_CONCURRENCY_EXCEPTIONS_TO_RETRY, ConcurrencyError):
            raise
        except Exception as error:
            return {'error': str(error)}, False
        self._maybe_publish_ui_action(text, name, call_id)
        self._maybe_publish_record_written(name)
        self._settle_tool_cost(name, text)
        if previews and isinstance(text, str):
            text += '\n\n' + '\n\n'.join(f'![image set]({url})' for url in previews)
        elif previews and isinstance(text, dict):
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

    @staticmethod
    def _inline_call(spec: dict) -> tuple[str, object]:
        """Return the requested tool name and the arguments of a ``tool_load`` call."""
        arguments = spec.get('arguments')
        if arguments is None:
            arguments = {
                k: v for k, v in spec.items() if k not in ('name', 'arguments')
            }
        return str(spec.get('name') or '').strip(), arguments

    def _dispatch_tool_load(self, arguments: dict, call_id: str) -> dict:
        """Load tool schemas by name and optionally run an inline call."""
        requested = arguments.get('names') if isinstance(arguments, dict) else None
        names = [
            str(item).strip()
            for item in (requested if isinstance(requested, list) else [])
            if isinstance(item, (str, int)) and str(item).strip()
        ]
        if not names:
            return {
                'error': "Argument 'names' must be a non-empty list of tool name strings."
            }
        catalog = {entry['name']: entry for entry in self._get_filtered_catalog()}
        loaded, unknown = {}, []
        for name in names:
            if resolved := self._resolve_tool_name(name, catalog):
                loaded[resolved] = {
                    'description': catalog[resolved].get('description') or '',
                    'inputSchema': catalog[resolved].get('inputSchema')
                    or {'type': 'object', 'properties': {}},
                }
            else:
                unknown.append(name)
        if loaded:
            self.expanded_tool_names = list(
                dict.fromkeys([*(self.expanded_tool_names or []), *loaded])
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
        if call_spec := arguments.get('call'):
            response['call'] = self._dispatch_tool_load_inline_call(
                call_spec, loaded, call_id
            )
        return response

    def _dispatch_tool_load_inline_call(
        self, call_spec, loaded: dict, parent_call_id: str
    ) -> dict:
        """Execute a tool call bundled into a ``tool_load`` request.

        Its file payload is stored here, so the nested result never reaches the
        model or the event log as raw base64.
        """
        if not isinstance(call_spec, dict):
            return {
                'error': '`call` must be an object with `name` and optional `arguments`.'
            }
        requested, arguments = self._inline_call(call_spec)
        if not requested:
            return {'error': '`call.name` is required.'}
        if not (target := self._resolve_tool_name(requested, loaded)):
            return {
                'error': (
                    f'`call.name` {requested!r} must be one of the just-loaded names; '
                    'include it in `names` and try again.'
                )
            }
        if not isinstance(arguments, dict):
            return {'error': '`call.arguments` must be an object.'}
        call = {
            'name': target,
            'arguments': arguments,
            'call_id': f'{parent_call_id}__{target}',
        }
        self._record_tool_call(call)
        result, ok = self._dispatch_tool_call(target, arguments, call['call_id'])
        result = self._persist_tool_file(result)
        self._append_tool_result(call, result, result)
        return {'name': target, 'output': result, 'ok': ok}

    def _maybe_publish_ui_action(self, text, name: str, call_id: str) -> None:
        """Publish a UI action when a tool returns an Odoo action payload.

        A terminating tool also pins the view its action opens.
        """
        try:
            action = json.loads(text) if isinstance(text, str) else None
        except ValueError:
            return
        if isinstance(action, dict) and str(action.get('type')).startswith(
            'ir.actions.'
        ):
            self._publish_event(
                'ui_action', {'call_id': call_id, 'name': name, 'action': action}
            )
            if name in self._get_terminating_tools() and (
                payload := self._view_context_from_action(name, action)
            ):
                self._write_view_context(payload)

    def _maybe_publish_record_written(self, name: str) -> None:
        """Tell the screens showing the pinned record that a write tool ran."""
        pinned = self.view_context or {}
        if (
            pinned.get('kind') == 'record'
            and get_tool_index(self.env).get(name, {}).get('category') == 'write'
        ):
            self._publish_event(
                'record_written', {'model': pinned['model'], 'id': pinned['id']}
            )

    def _view_context_from_action(self, tool_name: str, action: dict) -> dict | None:
        """Derive a view-context payload from an Odoo action, or ``None``."""
        if not (res_model := action.get('res_model')):
            return None
        if tool_name == 'open_record' or action.get('view_mode') == 'form':
            if not (res_id := action.get('res_id')):
                return None
            record = self.env[res_model].browse(int(res_id)).exists()
            return {
                'kind': 'record',
                'model': res_model,
                'id': int(res_id),
                'display_name': (record.has_access('read') and record.display_name)
                or str(res_id),
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

    def _settle_tool_cost(self, name: str, text) -> None:
        """Charge what the image tool spent to the session's cost ledger.

        ``generate_image`` is the only tool that spends money of its own, priced
        by the image model this session resolved, never one the result names.
        """
        if (
            name != 'generate_image'
            or not isinstance(text, str)
            or '"cost"' not in text
        ):
            return
        try:
            cost = json.loads(text).get('cost')
        except (ValueError, AttributeError):
            return
        if (
            isinstance(cost, dict)
            and isinstance(cost.get('usage'), dict)
            and (record := self._resolve_model_for('image'))
        ):
            self._accrue_usage(cost['usage'], record)

    def _persist_tool_file(self, result) -> object:
        """Store a tool's file payload and swap its base64 for a download URL.

        The registry JSON-encodes a tool's dict result, so the payload usually
        arrives as text and is decoded before the swap. The reported mimetype is
        the stored one, not the transport content type the tool sent.
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
        stored = {
            **rest,
            'mimetype': attachment.mimetype,
            'attachment_id': attachment.id,
            'url': f'/web/content/{attachment.id}?download=1',
        }
        if attachment.mimetype in IMAGE_MIMETYPES:
            stored['image_url'] = f'/web/image/{attachment.id}'
        return stored

    def _append_tool_output_with_vision(
        self, outputs: list, call_id: str, result
    ) -> object:
        """Append a tool output, holding its images back until the round ends.

        File payloads are stored first; a result longer than the context window
        reaches the model cut to it, with a marker saying so.
        :return: the cleaned, text-only result for event logging
        """
        result = self._persist_tool_file(result)
        cleaned = strip_images(result)
        attachments = self.env['ir.attachment']
        if specs := image_specs(result):
            if self._resolve_provider().supports_vision:
                for spec in specs[:TOOL_VISION_MAX_IMAGES]:
                    data = spec['data']
                    if data.startswith('data:'):
                        data = data.partition(',')[2]
                    if spec['mimetype'] not in IMAGE_MIMETYPES or not (
                        0 < len(data) <= TOOL_VISION_MAX_B64_CHARS
                    ):
                        continue
                    with contextlib.suppress(UserError):
                        attachments |= (
                            self.env['ir.attachment']
                            .sudo()
                            ._ai_create_from_upload(
                                spec['name'], spec['mimetype'], data, res_id=self.id
                            )
                        )
            if not attachments:
                cleaned = note_vision_unavailable(cleaned)
        output = build_tool_call_output(call_id, cleaned)
        text = output['output']
        if len(text) > (limit := self._resolve_context_window()):
            output['output'] = (
                f'{text[:limit]}\n\n[... tool result truncated: {len(text) - limit} '
                f'of {len(text)} characters dropped to fit the context window. '
                'Narrow the query with filters or a limit, or use aggregation '
                'to retrieve the rest.]'
            )
        outputs.append(output)
        if attachments:
            self.deferred_vision_attachment_ids = list(
                dict.fromkeys(
                    [*(self.deferred_vision_attachment_ids or []), *attachments.ids]
                )
            )
        return cleaned

    def _flush_deferred_vision(self, outputs: list) -> list:
        """Return ``outputs`` with the round's held-back images in one user entry."""
        if not (ids := self.deferred_vision_attachment_ids):
            return outputs
        self.deferred_vision_attachment_ids = False
        entry = self._build_user_entry(
            None, self.env['ir.attachment'].browse(ids).exists()
        )
        return [*outputs, {**entry, '_vision_entry': True}] if entry else outputs

    def _append_tool_result(self, call: dict, result, logged) -> None:
        """Append the transcript event of a tool result with the sources it cites.

        The source icon is the app a record belongs to, which only the server
        can tell.
        """
        event = {
            'kind': 'tool_result',
            'name': call['name'],
            'result': logged,
            'call_id': call['call_id'],
        }
        if sources := extract_sources(call['name'], call.get('arguments'), result):
            icons = self.env['ir.model']._ai_source_icons()
            for source in sources:
                if icon := icons.get(source.get('res_model')):
                    source['icon'] = icon
            event['sources'] = sources
        self._append_event(event)

    def _record_tool_result(
        self,
        outputs: list,
        call_id: str,
        name: str,
        output_result,
        log_result=None,
        arguments: dict | None = None,
    ) -> None:
        """Append a tool output and record the matching result event."""
        cleaned = self._append_tool_output_with_vision(outputs, call_id, output_result)
        self._append_tool_result(
            {'call_id': call_id, 'name': name, 'arguments': arguments},
            output_result,
            cleaned if log_result is None else log_result,
        )

    def _log_denied_call(self, call: dict, result: dict) -> None:
        """Write the tool log row of a call the chat refused, as a tool call would."""
        if not config.get('mcp_logging', True):
            return
        arguments = call.get('arguments')
        tool = self.env['muk_mcp.tool'].with_context(**self._tool_dispatch_context())
        self.env['muk_mcp.log'].log(
            **tool._tool_log_values(
                name=call['name'],
                env=self.env,
                arguments=arguments,
                model_name=arguments.get('model')
                if isinstance(arguments, dict)
                else None,
                status='denied',
                text=None,
                info={},
                error=': '.join(
                    filter(None, (result.get('error'), result.get('reason')))
                ),
                duration_ms=0,
            )
        )

    def _record_tool_call(self, call: dict) -> None:
        """Record a tool-call event with any subclass-provided extras."""
        self._append_event(
            {
                'kind': 'tool_call',
                'name': call['name'],
                'arguments': call['arguments'],
                'call_id': call['call_id'],
                **self._tool_call_event_extra(call),
            }
        )

    def _tool_call_event_extra(self, call: dict) -> dict:
        """Return extra fields to attach to a tool-call event."""
        return {}

    def _skip_tool_call(
        self, outputs: list, call: dict, reason: str, log_result=None
    ) -> None:
        """Record a call the round refuses and answer it with the reason."""
        result = {'error': reason}
        self._record_tool_call(call)
        self._log_denied_call(call, result)
        self._record_tool_result(
            outputs, call['call_id'], call['name'], result, log_result=log_result
        )

    def _client_action_deferred(self, call: dict) -> str | None:
        """Return a skip reason when the call cannot join the open action batch.

        Extension modules that gate single client actions, behind an approval
        say, return a reason so the call is skipped instead of clobbering the
        pending batch.
        """
        return None

    def _register_client_action(self, call: dict) -> None:
        """Add a client-executed tool call to the batch awaiting the client."""
        pending = self.pending_ask or {}
        if pending.get('kind') != 'client_action':
            pending = {
                'kind': 'client_action',
                'registered_at': fields.Datetime.to_string(fields.Datetime.now()),
                'actions': [],
                'results': {},
            }
        action = {key: call[key] for key in ('call_id', 'name', 'arguments')}
        self.pending_ask = {**pending, 'actions': [*pending['actions'], action]}
        self._record_tool_call(call)
        self._append_event({'kind': 'client_action', **action})

    def _register_ask_user(self, call: dict) -> None:
        """Register a pending question from an ``ask_user`` tool call."""
        arguments = call['arguments'] or {}
        ask = {
            'call_id': call['call_id'],
            'text': arguments.get('question'),
            'options': arguments.get('options'),
            'resolution': arguments.get('resolution') or 'text',
            'preview': clean_ask_preview(arguments.get('preview')),
        }
        self.pending_ask = {'kind': 'question', **ask}
        self._append_event({'kind': 'ask_user', **ask})

    def _resume_turn(self, continuation: list, event: dict | None = None) -> None:
        """Append a pause's continuation and event, clear it, and resume the turn."""
        self._extend_conversation(continuation)
        if event:
            self._append_event(event)
        self._transition_state(
            'running',
            values={
                'pending_ask': False,
                'claimed_at': False,
                'turn_wallclock_spent': 0.0,
                'turn_cost_spent': 0.0,
            },
        )
        self._trigger_worker()

    def _require_pending_client_action(self, call_id: str | None = None) -> dict:
        """Return the pending client action batch, validating state and call id.

        :raise UserError: when the session is not awaiting this client action
        """
        pending = dict(self.pending_ask or {})
        if self.state != 'waiting' or pending.get('kind') != 'client_action':
            raise UserError(self.env._('Session is not waiting for a client action.'))
        results = pending.get('results') or {}
        if call_id is not None and call_id not in {
            action.get('call_id')
            for action in pending.get('actions') or []
            if action.get('call_id') not in results
        }:
            raise UserError(
                self.env._('Client action call id does not match a pending action.')
            )
        return pending

    def _apply_client_result(self, pending: dict, call_id: str, result) -> None:
        """Record one client tool result and resume once the batch completes."""
        actions = pending.get('actions') or []
        pending['results'] = {**(pending.get('results') or {}), call_id: result}
        self._append_event(
            {
                'kind': 'client_action_result',
                'call_id': call_id,
                'name': next(
                    (a.get('name') for a in actions if a.get('call_id') == call_id),
                    None,
                ),
                'result': strip_images(result),
            }
        )
        if any(action.get('call_id') not in pending['results'] for action in actions):
            self._transition_state('waiting', values={'pending_ask': pending})
            return
        continuation = []
        for action in actions:
            self._append_tool_output_with_vision(
                continuation, action['call_id'], pending['results'][action['call_id']]
            )
        self._resume_turn(self._flush_deferred_vision(order_outputs(continuation)))

    def _check_approval_gate(self, name: str, arguments: dict) -> dict:
        """Decide whether a tool call dispatches, auto-approves, or pauses.

        A ``tool_load`` request is judged by the call it runs inline.
        """
        if name == TOOL_LOAD_TOOL['name'] and isinstance(arguments.get('call'), dict):
            name, arguments = self._inline_call(arguments['call'])
            name = name.rpartition('.')[2]
        approval = self.env['muk_ai.approval']
        if self._effective_approval_mode() == 'off' or not (
            isinstance(arguments, dict)
            and (risk := approval._assess_risk(name, arguments))
        ):
            return {'action': 'dispatch'}
        if risk['signature'] in (self.approved_signatures or []):
            return {'action': 'auto_approved', 'risk': risk}
        preview = approval._build_preview(name, arguments) or {'arguments': arguments}
        return {'action': 'pause', 'risk': risk, 'preview': preview}

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
        ask = {
            'call_id': call['call_id'],
            'text': risk.get('reason') or '',
            'resolution': 'yesno',
            'preview': gate['preview'],
        }
        self._append_event({'kind': 'ask_user', **ask})
        self._transition_state(
            'waiting',
            values={
                'pending_ask': {
                    'kind': 'approval',
                    **ask,
                    'name': call['name'],
                    'arguments': call['arguments'],
                    'risk': risk,
                    'tool_calls': tool_calls,
                    'outputs': outputs,
                    'resume_index': index,
                    'has_terminating': has_terminating,
                }
            },
        )

    def _record_approval_audit(
        self, decision: str, call: dict, risk: dict, reject_reason: str | None = None
    ) -> None:
        """Create an approval audit record for a tool-call decision."""
        arguments = call.get('arguments') or {}
        self.env['muk_ai.approval'].sudo().create(
            {
                'session_id': self.id,
                'agent_id': self.agent_id.id,
                'user_id': self.env.user.id,
                'decision': decision,
                'tool_name': risk.get('tool') or '',
                'res_model': risk.get('model') or '',
                'res_ids': risk.get('ids') or [],
                'method': risk.get('method') or '',
                'reason': risk.get('reason') or '',
                'signature': risk.get('signature') or '',
                'args_proposed': arguments,
                'args_executed': arguments,
                'reject_reason': reject_reason or False,
            }
        )

    def _decide_tool(self, decision: str, reason: str | None = None) -> dict:
        """Apply the user's decision on the pending tool call and resume the round.

        :raise AccessError: when the caller may only read the session
        :raise UserError: when the session is not awaiting approval
        """
        self.check_access('write')
        pending = dict(self.pending_ask or {})
        if self.state != 'waiting' or pending.get('kind') != 'approval':
            raise UserError(self.env._('Session is not waiting for approval.'))
        risk = pending.get('risk') or {}
        if decision == 'approved_session' and (signature := risk.get('signature')):
            self.approved_signatures = [*(self.approved_signatures or []), signature]
        self._record_approval_audit(decision, pending, risk, reject_reason=reason)
        self._append_event(
            {'kind': 'approval', 'call_id': pending['call_id'], 'decision': decision}
        )
        self._resume_tool_round(
            pending, approved=decision != 'rejected', reject_reason=reason
        )
        if self.state == 'running':
            self._trigger_worker()
        return self.get_snapshot()

    def _resume_tool_round(
        self, paused: dict, approved: bool, reject_reason: str | None = None
    ) -> None:
        """Resume a paused tool round after an approval decision.

        :raise UserError: when the session lock cannot be acquired
        """
        with self._session_lock():
            call = {key: paused[key] for key in ('call_id', 'name', 'arguments')}
            outputs = list(paused.get('outputs') or [])
            has_terminating = bool(paused.get('has_terminating'))
            if approved:
                has_terminating |= self._dispatch_and_record(call, outputs)
            else:
                self._record_tool_call(call)
                result = {'error': 'rejected_by_user', 'reason': reject_reason or ''}
                self._log_denied_call(call, result)
                self._record_tool_result(
                    outputs,
                    call['call_id'],
                    call['name'],
                    result,
                    arguments=call['arguments'],
                )
            self._transition_state(
                'running', values={'pending_ask': False, 'claimed_at': False}
            )
            self._process_tool_round(
                list(paused.get('tool_calls') or []),
                outputs,
                paused.get('resume_index', 0) + 1,
                has_terminating=has_terminating,
            )

    def _execute_tool_call(
        self,
        call: dict,
        tool_calls: list,
        outputs: list,
        index: int,
        has_terminating: bool,
    ) -> bool | None:
        """Run one tool call through the approval gate and record its result.

        :return: whether a terminating tool ran, ``None`` when the round paused
        """
        gate = self._check_approval_gate(call['name'], call['arguments'])
        if gate['action'] == 'pause':
            self._enter_waiting_approval(
                call, tool_calls, outputs, index, has_terminating, gate
            )
            return None
        if gate['action'] == 'auto_approved':
            self._record_approval_audit('auto_approved', call, gate['risk'])
        return self._dispatch_and_record(call, outputs)

    def _dispatch_and_record(self, call: dict, outputs: list) -> bool:
        """Dispatch a tool call between worker heartbeats and record its result.

        :return: whether a terminating tool ran
        """
        self._record_tool_call(call)
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
        """Run a round of tool calls, returning the terminating state or ``None``.

        ``None`` means the round paused or waits on the user or the client.
        """
        has_ask_user = any(call.get('name') == 'ask_user' for call in tool_calls)
        waiting = False
        client_names = self._client_tool_names()
        for index in range(start_index, len(tool_calls)):
            call = tool_calls[index]
            name, log_result, skip = call['name'], None, None
            if index >= MAX_TOOL_CALLS_PER_ROUND:
                skip = 'tool_call_limit_exceeded'
            elif call.get('_parse_error'):
                skip = call['_parse_error']
            elif name == 'ask_user':
                if not self._can_ask_user():
                    skip = 'ask_user_unavailable'
                elif waiting:
                    skip = 'ask_user_already_pending'
                else:
                    self._register_ask_user(call)
                    waiting = True
                    continue
            elif name in client_names and not has_ask_user and not has_terminating:
                if waiting and (self.pending_ask or {}).get('kind') == 'client_action':
                    skip = self._client_action_deferred(call)
                elif waiting:
                    skip = 'client_action_already_pending'
                if not skip:
                    self._register_client_action(call)
                    waiting = True
                    continue
            elif has_ask_user or waiting or has_terminating:
                skip = SKIP_REASONS[
                    'ask_user'
                    if has_ask_user
                    else 'client'
                    if waiting
                    else 'terminating'
                ]
                log_result = {'error': 'skipped'}
            else:
                outcome = self._execute_tool_call(
                    call, tool_calls, outputs, index, has_terminating
                )
                if outcome is None:
                    return None
                has_terminating |= outcome
                if name == TOOL_LOAD_TOOL['name']:
                    client_names = self._client_tool_names()
                continue
            self._skip_tool_call(outputs, call, skip, log_result=log_result)
        ordered = order_outputs(outputs)
        if not waiting:
            ordered = self._flush_deferred_vision(ordered)
        self._extend_conversation(ordered)
        if waiting:
            self._transition_state('waiting')
            return None
        return has_terminating
