from __future__ import annotations

import psycopg2
from markupsafe import Markup, escape

from odoo import api, fields, models
from odoo.tools import SQL

from odoo.addons.muk_ai.tools.conversation import cap_log_payload, short_error_reason


class AISessionNotify(models.AbstractModel):
    """Transcript log, bus broadcasts and owner notifications of a chat."""

    _name = 'muk_ai.session.notify'
    _description = 'AI Session Notifications'
    _explanation = (
        'The part of a chat that records its transcript and tells the people '
        'who follow it what changed.'
    )

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    notification_unread = fields.Boolean(
        string='Notification Unread',
        readonly=True,
        copy=False,
    )

    awaiting_user = fields.Boolean(
        compute='_compute_awaiting_user',
        string='Awaiting User',
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _audience_users(self) -> models.BaseModel:
        """Return the users whose chat list shows this session."""
        return self.user_id | self.share_user_ids

    def _list_payload(self) -> dict:
        """Return what a chat list shows of this session."""
        return {
            'session_id': self.id,
            'name': self.name,
            'state': self.state,
            'awaiting_user': self.awaiting_user,
        }

    def _notify_share_change(self, previous: models.BaseModel) -> None:
        """Tell the people a chat was just given to, or taken from.

        A reader who lost it is told the way a deletion is told, so the chat and
        its channel leave their surface; a new owner is still in the audience.
        """
        (previous - self._audience_users())._bus_send(
            'muk_ai.session_state', {'session_id': self.id, 'deleted': True}
        )
        readers = self.share_user_ids - previous
        readers._bus_send('muk_ai.session_state', self._list_payload())
        self._post_notification(
            readers,
            self.env._('Chat shared with you'),
            self.env._(
                '%(name)s shared the chat "%(chat)s" with you.',
                name=self.env.user.name,
                chat=self.name or '',
            ),
        )

    def _state_metrics(self) -> dict:
        """Return the public state and usage metrics broadcast on the bus."""
        return {
            'state': self.state,
            'iteration_count': self.iteration_count,
            'total_input_tokens': self.total_input_tokens,
            'total_output_tokens': self.total_output_tokens,
            'last_input_tokens': self.last_input_tokens,
            'turn_usage': self.turn_usage or {},
            'context_window': self._resolve_context_window(),
            'view_context': self.view_context or None,
            'pending_ask': self._public_pending_ask(),
            'override_approval_mode': self.override_approval_mode or False,
            'effective_approval_mode': self._effective_approval_mode(),
            'override_reasoning_effort': self.override_reasoning_effort or False,
            'effective_reasoning_effort': self._effective_reasoning_effort() or False,
            'reasoning_effort_options': self._reasoning_effort_options(),
            'agent_reasoning_effort': self.agent_id.reasoning_effort or False,
            'total_cost': self.total_cost,
        }

    def _publish_event(self, event_type: str, payload: dict) -> None:
        """Broadcast a session event and any derived state notifications."""
        self._bus_send(
            'muk_ai.event',
            {'session_id': self.id, 'type': event_type, 'payload': payload},
        )
        if event_type == 'state':
            self._audience_users()._bus_send(
                'muk_ai.session_state',
                {**self._list_payload(), **self._state_metrics()},
            )
            self._notify_state_transition(payload)
        elif event_type == 'rename':
            self._audience_users()._bus_send(
                'muk_ai.session_state', self._list_payload()
            )

    def _append_event(self, entry: dict) -> models.BaseModel:
        """Append an event with the next free sequence and broadcast it.

        A ``private_user_id`` key keeps the line to that one user.
        """
        entry = dict(entry)
        private = self.env['res.users'].browse(entry.pop('private_user_id', None))
        entry.setdefault('at', fields.Datetime.now().isoformat())
        event = self.env['muk_ai.session.event'].sudo()
        self.env.cr.execute(
            SQL(
                'SELECT COALESCE(MAX(sequence), -1) + 1 '
                'FROM muk_ai_session_event WHERE session_id = %s',
                self.id,
            )
        )
        sequence = self.env.cr.fetchone()[0]
        for _attempt in range(5):
            try:
                with self.env.cr.savepoint():
                    event = event.create(
                        {
                            'session_id': self.id,
                            'sequence': sequence,
                            'kind': entry.get('kind') or '',
                            'payload': entry,
                            'private_user_id': private.id,
                        }
                    )
                break
            except psycopg2.errors.UniqueViolation:
                sequence += 1
        payload = cap_log_payload({**entry, 'event_id': event.id, 'sequence': sequence})
        if private:
            private._bus_send(
                'muk_ai.event',
                {'session_id': self.id, 'type': 'log', 'payload': payload},
            )
        else:
            self._publish_event('log', payload)
        return event

    def _should_notify_state(self) -> bool:
        """Return whether a terminal state is worth telling the owner about.

        True for a session somebody started and walked away from. A surface
        that shows the run as it happens overrides this: it already told them.
        """
        return True

    def _notify_state_transition(self, payload: dict) -> None:
        """Toast and badge a terminal state; a wait for the owner also reaches the inbox."""
        state = payload.get('state')
        context = self.env.context
        if (
            state not in ('done', 'waiting', 'error')
            or not self._should_notify_state()
            or context.get('muk_ai_state_unchanged')
            or (
                state == 'done'
                and (self.pending_ids or context.get('muk_ai_skip_done_notification'))
            )
        ):
            return
        ask = payload.get('ask') or self.pending_ask or {}
        ask_kind = ask.get('kind') if isinstance(ask, dict) else None
        message = self._notification_message(state, payload, ask_kind)
        self.notification_unread = True
        self.user_id._bus_send(
            'muk_ai.session_notification',
            {
                'session_id': self.id,
                'session_name': self.name,
                'state': state,
                'ask_kind': ask_kind,
                'message': message,
                'at': fields.Datetime.to_string(fields.Datetime.now()),
            },
        )
        if state == 'waiting':
            self._post_notification(
                self.user_id.filtered(lambda user: user.notification_type == 'inbox'),
                self.name,
                message,
            )
        self._push_notification_badge(self.user_id)

    def _notification_message(
        self, new_state: str, payload: dict, ask_kind: str | None
    ) -> str:
        """Return what the notification of a terminal state says about the chat."""
        if new_state == 'done':
            return self.env._('Finished')
        if new_state == 'error':
            raw = payload.get('error') or self.error_message
            return self.env._(
                'Stopped: %(reason)s',
                reason=short_error_reason(raw) if raw else self.env._('unknown error'),
            )
        if ask_kind == 'approval':
            return self.env._('Needs your approval before running a tool')
        return self.env._('Waiting for your answer')

    def _post_notification(
        self, users: models.BaseModel, title: str, message: str
    ) -> None:
        """Notify ``users`` about the chat, each the way their preference says.

        The inbox with web or mobile push, or one email; the message opens the chat.
        """
        if not users:
            return
        mail_message = self.env['mail.thread'].message_notify(
            partner_ids=users.partner_id.ids,
            model=self._name,
            res_id=self.id,
            author_id=self.env.ref('base.partner_root').id,
            subject=title,
            body=Markup('<p>%s</p>') % escape(message),
        )
        mail_message.sudo().muk_ai_session_id = self.id

    @api.model
    def _notification_badge_payload(self, user: models.BaseModel) -> dict:
        """Return the badge count, unread session ids and per-space totals.

        The space totals travel with the badge so the sidebar never holds a
        second, staler copy.
        """
        domain = [('user_id', '=', user.id), ('notification_unread', '=', True)]
        ids = self.env['muk_ai.session'].sudo().search(domain).ids
        return {
            'count': len(ids),
            'session_ids': ids,
            'space_unread': self.env['muk_ai.space']
            .with_user(user)
            .count_sessions(ids),
        }

    def _push_notification_badge(self, user: models.BaseModel) -> None:
        """Push the attention badge payload to the user's systray."""
        user._bus_send(
            'muk_ai.notification_badge', self._notification_badge_payload(user)
        )

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    def notification_badge(self) -> dict:
        """Return the attention badge payload for the current user."""
        return self._notification_badge_payload(self.env.user)

    def dismiss_notifications(self) -> bool:
        """Clear the attention flag and mark inbox notifications read.

        The flag belongs to the owner, so reading a chat somebody shared with
        you leaves theirs alone rather than attempting a write you may not make.
        """
        messages = (
            self.env['mail.message']
            .sudo()
            .search([('muk_ai_session_id', 'in', self.ids)])
        )
        messages.with_user(self.env.user).set_message_done()
        self.filtered(
            lambda session: (
                session.user_id == self.env.user and session.notification_unread
            )
        ).notification_unread = False
        self._push_notification_badge(self.env.user)
        return True

    # ----------------------------------------------------------
    # Compute
    # ----------------------------------------------------------

    @api.depends('state')
    def _compute_awaiting_user(self) -> None:
        """Flag the chats that wait for their owner to answer or approve."""
        for record in self:
            record.awaiting_user = record.state == 'waiting'
