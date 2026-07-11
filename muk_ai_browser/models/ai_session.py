from __future__ import annotations

import json

from odoo import _, fields, models

BROWSER_MUTATING_TOOLS = frozenset(
    {
        'click',
        'fill',
        'select_option',
        'press_key',
        'navigate',
        'navigate_back',
    },
)


class AISession(models.Model):
    """Bridge the MuK AI agent loop to attached browser actuator sessions."""

    _inherit = 'muk_ai.session'

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _active_browser_sessions(self) -> models.BaseModel:
        """Return active browser sessions on this AI session owned by its user."""
        self.ensure_one()
        sessions = (
            self.env['muk_ai_browser.session']
            .sudo()
            .search(
                [
                    ('ai_session_id', '=', self.id),
                    ('active', '=', True),
                ],
            )
        )
        return sessions.filtered(
            lambda session: (
                not session.key_id or session.key_id.user_id.id == self.user_id.id
            ),
        )

    def _has_active_browser_session(self) -> bool:
        """Return whether an owned, active browser session is attached."""
        return bool(self.id) and bool(self._active_browser_sessions())

    def _browser_event_type(self, event_type: str, payload: dict) -> str:
        """Map a published AI event to a browser event-queue type."""
        if event_type == 'state':
            return 'state'
        if event_type == 'log' and (payload or {}).get('kind') == 'ask_user':
            return 'ask'
        return 'event'

    def _browser_last_origin(self) -> str:
        """Return the most recently reported page origin across browser sessions."""
        sessions = self._active_browser_sessions().sorted(
            lambda session: session.last_activity or fields.Datetime.now(),
            reverse=True,
        )
        for session in sessions:
            if session.last_origin:
                return session.last_origin
        return ''

    # ----------------------------------------------------------
    # Catalog
    # ----------------------------------------------------------

    def _get_filtered_catalog(self) -> list[dict]:
        """Drop client-executed tools when no browser session is attached.

        Visibility gating: ``execute == 'client'`` tools are only exposed to the
        model (and treated as client tools) while an active browser session backs
        this AI session.
        """
        catalog = super()._get_filtered_catalog()
        if self.id and self._has_active_browser_session():
            return catalog
        return [
            entry
            for entry in catalog
            if (entry.get('_meta') or {}).get('execute') != 'client'
        ]

    def _get_essential_tool_names(self) -> list[str]:
        """Promote client-executed tools to essential while a browser is attached.

        Loading their full schemas upfront lets the model call browser tools
        directly, so they hit the client-action pause in the tool round instead
        of being loaded and inline-called through ``tool_load`` (which would
        execute them without pausing for the client).
        """
        names = list(super()._get_essential_tool_names())
        if self.id and self._has_active_browser_session():
            for entry in self._get_filtered_catalog():
                if (entry.get('_meta') or {}).get('execute') == 'client':
                    if entry['name'] not in names:
                        names.append(entry['name'])
        return names

    # ----------------------------------------------------------
    # Prompt
    # ----------------------------------------------------------

    def _effective_system_prompt(self) -> str:
        """Append live-browser context so the agent reads the page itself.

        With a browser session attached, tell the model it is connected to the
        user's current tab so it calls ``read_page``/``click``/``fill`` directly
        instead of asking the user to paste page content or a URL.
        """
        prompt = super()._effective_system_prompt()
        if not (self.id and self._has_active_browser_session()):
            return prompt
        origin = self._browser_last_origin() or _('the page they are viewing')
        note = _(
            'You are connected to the live web browser the user is working in, '
            'through the MuK AI Browser extension. The user is currently on '
            '%(origin)s. When the user says "this page", "this product", "here" '
            'or similar, they mean the page open in the browser right now. Read '
            'it yourself with the read_page tool. Do not ask the user to paste '
            'page content or a URL, and do not ask which page they mean. Use '
            'click, fill, select_option, scroll, navigate and the other browser '
            'tools to act on that page directly. Ask a clarifying question only '
            'when the task is genuinely ambiguous after you have read the page.',
            origin=origin,
        )
        return f'{prompt}\n\n{note}'

    # ----------------------------------------------------------
    # Safety
    # ----------------------------------------------------------

    def _browser_risky_keywords(self) -> list[str]:
        """Return the configured risky keywords forcing an approval gate."""
        raw = (
            self.env['ir.config_parameter']
            .sudo()
            .get_param('muk_ai_browser.risky_keywords', '')
        )
        return [
            token.strip().lower() for token in (raw or '').split(',') if token.strip()
        ]

    def _browser_args_risky(self, call: dict, origin: str) -> bool:
        """Return whether a call's arguments or origin match a risky keyword."""
        keywords = self._browser_risky_keywords()
        if not keywords:
            return False
        blob = '{} {}'.format(
            json.dumps(call.get('arguments') or {}, default=str),
            origin or '',
        ).lower()
        return any(keyword in blob for keyword in keywords)

    def _browser_should_gate(self, call: dict) -> bool:
        """Decide whether a client action must pause for user approval.

        Gating fires for mutating browser tools when the per-site mode is
        ``'ask'``, when the action is a navigate-away or form submit, or when
        the arguments or origin match a configured risky keyword.
        """
        name = call.get('name')
        if name not in BROWSER_MUTATING_TOOLS:
            return False
        origin = self._browser_last_origin()
        mode = self.env['muk_ai_browser.permission']._mode_for(self.user_id, origin)
        if mode == 'ask':
            return True
        if name in ('navigate', 'navigate_back'):
            return True
        if name == 'fill' and (call.get('arguments') or {}).get('submit'):
            return True
        return self._browser_args_risky(call, origin)

    def _browser_enter_action_approval(self, call: dict) -> None:
        """Pause the round awaiting approval of a risky client action.

        Sets an ``approval``-kind pending tagged so the resume path falls
        through to registering the client action instead of dispatching it
        server-side. The state write and broadcast are finalised by the
        caller (``_process_tool_round``), mirroring ``_register_ask_user``.
        """
        origin = self._browser_last_origin()
        reason = _(
            'Approve the "%(name)s" browser action on %(origin)s before it runs.',
            name=call['name'],
            origin=origin or _('the current page'),
        )
        preview = {
            'name': call['name'],
            'arguments': call['arguments'],
            'origin': origin,
        }
        self.pending_ask = {
            'kind': 'approval',
            '_browser_action': True,
            'origin': origin,
            'call_id': call['call_id'],
            'name': call['name'],
            'arguments': call['arguments'],
            'text': reason,
            'resolution': 'yesno',
            'preview': preview,
            'risk': {
                'reason': reason,
                'signature': 'browser:{}:{}'.format(origin, call['name']),
            },
            'tool_calls': [],
            'outputs': [],
            'resume_index': 0,
            'has_terminating': False,
        }
        self._append_event(
            {
                'kind': 'ask_user',
                'call_id': call['call_id'],
                'text': reason,
                'resolution': 'yesno',
                'preview': preview,
            },
        )

    # ----------------------------------------------------------
    # Bridge
    # ----------------------------------------------------------

    def _publish_event(self, event_type: str, payload: dict) -> None:
        """Mirror every published AI event onto the attached browser queues."""
        super()._publish_event(event_type, payload)
        if not self.id:
            return
        for session in self._active_browser_sessions():
            session._enqueue_event(
                self._browser_event_type(event_type, payload),
                {'type': event_type, 'payload': payload},
            )

    def _client_action_deferred(self, call: dict) -> str | None:
        """Defer gated actions instead of clobbering an open action batch."""
        if self.id and self._browser_should_gate(call):
            return (
                'skipped: approval required, call again after the pending '
                'client actions complete'
            )
        return super()._client_action_deferred(call)

    def _register_client_action(self, call: dict) -> None:
        """Gate risky client actions, else register and enqueue the action request."""
        if self.id and self._browser_should_gate(call):
            self._browser_enter_action_approval(call)
            return
        self._browser_register_action(call)

    def _browser_register_action(self, call: dict) -> None:
        """Register the client action and enqueue its browser ``action_request``."""
        super()._register_client_action(call)
        if not self.id:
            return
        for session in self._active_browser_sessions():
            session._enqueue_event(
                'action_request',
                {
                    'call_id': call['call_id'],
                    'name': call['name'],
                    'arguments': call['arguments'],
                },
            )

    def _resume_tool_round(
        self, paused: dict, approved: bool, reject_reason: str | None = None
    ) -> None:
        """Resume an approval pause, routing approved browser actions to the client.

        An approved browser-action approval does not dispatch server-side; it
        falls through to registering the client action so the extension still
        executes it, then re-enters the waiting state for the action result.
        """
        if approved and (paused or {}).get('_browser_action'):
            self._browser_register_action(
                {
                    'call_id': paused['call_id'],
                    'name': paused['name'],
                    'arguments': paused['arguments'],
                },
            )
            self.write({'state': 'waiting', 'claimed_at': False})
            self._publish_event(
                'state',
                {'state': 'waiting', 'ask': self._public_pending_ask()},
            )
            return
        super()._resume_tool_round(paused, approved, reject_reason=reject_reason)

    def approve_for_session(self) -> dict:
        """Approve the pending call and grant the origin ``follow_plan`` if browser."""
        pending = dict(self.pending_ask or {})
        if pending.get('_browser_action') and pending.get('origin'):
            self.env['muk_ai_browser.permission']._grant(
                self.user_id,
                pending['origin'],
            )
        return super().approve_for_session()
