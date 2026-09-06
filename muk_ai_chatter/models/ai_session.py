from __future__ import annotations

from contextlib import suppress

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.mail import plaintext2html

from odoo.addons.mail.tools.discuss import Store
from odoo.addons.muk_ai.tools import with_record_ctx
from odoo.addons.muk_ai_chatter.tools import (
    COMPOSE_INTERFACES,
    COMPOSE_TURN_REMINDER,
    MENTION_RULES,
    compose_addenda,
    compose_text_values,
    fenced,
    linkify_records,
    session_link,
)


class AISession(models.Model):
    """Link AI sessions to the business record they run for."""

    _inherit = 'muk_ai.session'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    res_model = fields.Char(
        string='Linked Model',
        help='Model of the business record this session is linked to.',
        index=True,
        copy=False,
    )

    res_id = fields.Many2oneReference(
        model_field='res_model',
        string='Linked Record',
        help='Identifier of the linked business record.',
        index=True,
        copy=False,
    )

    is_mention = fields.Boolean(
        string='Started by a Mention',
        help=(
            'Set when a mention in a conversation started this session. It '
            'decides the guard rails, so it is stored in its own right rather '
            'than read off the mention, which the author is free to delete.'
        ),
        copy=False,
    )

    mention_message_id = fields.Many2one(
        comodel_name='mail.message',
        string='Mention',
        help='Message whose agent mention started this session.',
        copy=False,
        ondelete='set null',
    )

    answer_message_id = fields.Many2one(
        comodel_name='mail.message',
        string='Answer',
        help='Message carrying the answer to the mention.',
        copy=False,
        ondelete='set null',
    )

    mention_context = fields.Text(
        string='Thread Snapshot',
        help=(
            'Conversation recorded on the record when the mention arrived. '
            'Frozen on purpose: chatter messages can be edited afterwards.'
        ),
        copy=False,
    )

    compose_interface = fields.Selection(
        selection=COMPOSE_INTERFACES,
        string='Composer',
        help='Composer this session is helping to write in.',
        copy=False,
    )

    compose_draft = fields.Text(
        string='Draft',
        help='Message the user had written when the writing helper was opened.',
        copy=False,
    )

    compose_selection = fields.Text(
        string='Selected Text',
        help='Part of the draft the user asked to have rewritten.',
        copy=False,
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _skill_scope_context(self) -> dict | None:
        """Stand the linked record in for a view the session never had.

        A mention or an automation runs without a screen, so a skill that acts
        on the record it was started from would otherwise be refused for want
        of a pinned view.
        """
        context = super()._skill_scope_context()
        if context:
            return context
        record = self._linked_record()
        if record is None or not self._owner_can_read(record):
            return None
        return {'kind': 'record', 'model': record._name, 'id': record.id}

    def _linked_record(self) -> models.BaseModel | None:
        """Return the linked business record, or ``None`` when unresolved."""
        if not self.res_model or not self.res_id or self.res_model not in self.env:
            return None
        record = self.env[self.res_model].sudo().browse(self.res_id)
        return record if record.exists() else None

    def _owner_can_read(self, record: models.BaseModel) -> bool:
        """Return whether the session owner may read the linked record."""
        owner = self.user_id or self.env.user
        return record.with_user(owner).has_access('read')

    def _enforce_tool_scope(self) -> str | None:
        """Hold a writing helper to read-only tools.

        It is asked for words, never for a change: the user has not sent
        anything yet, and nothing it drafts is worth a write.
        """
        if self.compose_interface:
            return 'read'
        return super()._enforce_tool_scope()

    def _effective_approval_mode(self) -> str:
        """Never pause a mention or a writing helper to ask for approval.

        A mention answers into a chatter nobody is watching a chat window for.
        Anything that pauses the run leaves the thread on "working on it" for
        good, so the agent is given no way to stop and ask: it answers with
        what it has. A writing helper has nothing to approve either — it runs
        read-only, and the overlay it draws in has no place to put a prompt.
        """
        if self.is_mention or self.compose_interface:
            return 'off'
        return super()._effective_approval_mode()

    def _can_ask_user(self) -> bool:
        """Refuse a mention or a writing helper the right to stop and ask.

        Nobody is watching the chat window of a session a mention started, so
        a question would hang the thread on "working on it" for good. The
        writing helper is watched, but by an overlay that offers a draft and
        two buttons — a question there would be a dead end. Both are told as
        much in their prompt, and the dispatcher refuses the call anyway.
        """
        if self.is_mention or self.compose_interface:
            return False
        return super()._can_ask_user()

    def _available_client_kinds(self) -> set[str]:
        """Offer no client-executed tool to a headless or overlay-bound run.

        Nothing hosts the chat window of a session a mention started, so any
        client tool would pend until a sweep. Every kind is dropped rather
        than the browser one alone: a kind another module contributes would
        pend just the same, and client tools bypass the read-only cap since
        they never reach the MCP layer. The writing helper draws no chat
        window either, so the same holds while it is attached to a composer.
        """
        if self.is_mention or self.compose_interface:
            return set()
        return super()._available_client_kinds()

    def _should_autoname(self) -> bool:
        """Keep the name a mention or a writing helper was opened under.

        A mention is named after its agent and its record, and a helper after
        what it is for. Retitling either after the first instruction sent to
        it — ``Shorten it`` — loses that and says nothing in its place.
        """
        if self.is_mention or self.compose_interface:
            return False
        return super()._should_autoname()

    def _should_notify_state(self) -> bool:
        """Stay quiet while a composer is showing the run as it happens.

        The writing helper streams into the panel the user is looking at and
        ends with a draft in front of them. Announcing the same run in the
        systray, and again in their inbox, would turn every rewrite into two
        notifications about something they just watched.
        """
        if self.compose_interface:
            return False
        return super()._should_notify_state()

    def _compose_target_changed(self, values: dict) -> bool:
        """Return whether the helper is being pointed at different text.

        The same helper answers every message a user writes, so what it said
        about the last one is still in its conversation. Asked to rewrite
        something else, it reads its own previous answer and hands it back
        again. A new piece of text is a new question, and starts clean; asking
        again about the same one keeps the conversation, which is what lets
        somebody say what they did not like about the first attempt.

        An empty composer is not the same text twice: there is no text, and
        nothing said about the last message belongs in the next one. Two
        follow-ups written from the same record would otherwise share a
        conversation, which is what the user sees when they take the second
        one into the chat window and read the first one above it.

        :param values: the composer context about to be written
        """
        draft = values.get('compose_draft') or ''
        if not draft:
            return True
        return (self.compose_draft or '', self.compose_selection or '') != (
            draft,
            values.get('compose_selection') or '',
        )

    def _reset_for_new_target(self) -> None:
        """Empty a reused helper, log and all, before it is pointed elsewhere.

        :meth:`clear` keeps the event log on purpose, which a helper has no
        use for. The log is re-read before it is dropped, as clearing writes
        a line of its own through ``sudo`` and leaves the cached one behind.
        """
        self.clear()
        self.invalidate_recordset(['event_ids'])
        self.event_ids.unlink()

    def _system_prompt_addenda(self) -> list[str]:
        """Append the mention rules, the composer context and the snapshot."""
        addenda = super()._system_prompt_addenda()
        if self.is_mention:
            addenda.append(MENTION_RULES)
        if self.compose_interface:
            addenda.extend(compose_addenda(self.compose_draft, self.compose_selection))
        if self.mention_context:
            addenda.append(fenced('thread_context', self.mention_context))
        return addenda

    def _build_request_inputs(self) -> list[dict]:
        """Extend request inputs with the linked record context when present."""
        inputs = super()._build_request_inputs()
        record = self._linked_record()
        if record is not None and self._owner_can_read(record):
            inputs = with_record_ctx(
                inputs,
                {
                    'kind': 'record',
                    'model': record._name,
                    'id': record.id,
                    'display_name': record.display_name,
                },
            )
        return inputs

    def _session_link(self, label: str | None = None) -> Markup:
        """Return a chatter link opening this session."""
        return session_link(self.id, label or self.display_name or _('AI Session'))

    def _post_chatter_mirror(self) -> None:
        """Post a chatter note on the linked record pointing at this session.

        A record that refuses the note — a model with its own posting rules, a
        chatter that is unavailable — costs the session nothing. Contained in a
        savepoint, not only in a ``suppress``: a statement that failed leaves
        the transaction aborted, and swallowing the exception without undoing
        the statement takes the caller down a moment later instead.
        """
        record = self._linked_record()
        if record is None or not hasattr(record, 'message_post'):
            return
        if not self._owner_can_read(record):
            return
        body = Markup('<p>%s</p>') % _(
            'AI session %(link)s started for this record.',
            link=self._session_link(),
        )
        with suppress(Exception), self.env.cr.savepoint():
            record.message_post(body=body, subtype_xmlid='mail.mt_note')

    # ----------------------------------------------------------
    # Helper Mention
    # ----------------------------------------------------------

    def _mention_answer_body(self) -> Markup:
        """Return the note body reporting where this mention has got to."""
        footer = Markup('<p class="text-muted small">%s</p>') % self._session_link(
            _('View the run')
        )
        if self.state == 'error':
            reason = self.error_message or _('unknown error')
            return (
                Markup('<p><i>%s</i></p>')
                % _('The agent could not answer: %(reason)s', reason=reason)
            ) + footer
        if self.state in ('done', 'stopped') and self.last_text:
            body = linkify_records(
                plaintext2html(self.last_text), lambda model: model in self.env
            )
            return body + footer
        if self.state in ('done', 'stopped'):
            return (Markup('<p><i>%s</i></p>') % _('The agent had nothing to add.')) + (
                footer
            )
        return Markup('<p><i>%s</i></p>') % _('Working on it…')

    def _post_mention_placeholder(self) -> None:
        """Answer the mention straight away with a note that fills in later.

        Posting before the agent has thought anything is the acknowledgement:
        the thread shows the mention was picked up, and the same note is
        rewritten in place as the run ends — one message, never a stream of
        partial ones.

        A thread that refuses the acknowledgement still gets the answer, which
        :meth:`_refresh_mention_answer` posts in its place. Contained in a
        savepoint like the mirror note, so a refusal undoes itself rather than
        leaving the transaction aborted under the run that goes on.
        """
        record = self._linked_record()
        if record is None or not hasattr(record, 'message_post'):
            return
        partner = self.agent_id.partner_id
        if not partner:
            return
        with suppress(Exception), self.env.cr.savepoint():
            self.answer_message_id = record.with_context(
                mail_post_autofollow=False,
                mail_post_autofollow_author_skip=True,
            ).message_post(
                body=self._mention_answer_body(),
                author_id=partner.id,
                message_type='comment',
                subtype_xmlid='mail.mt_comment',
                parent_id=self.mention_message_id.id or False,
            )

    def _refresh_mention_answer(self) -> None:
        """Rewrite the answer note with the state the run ended in.

        Only a mention answers into the thread. Every other session linked to
        a record — an automation run, a schedule — announces itself with the
        mirror note and keeps its output to itself, which is what the
        owner-only transcript fields are for.

        Posts the note instead when the placeholder never made it, so a
        mention always leaves an answer in the thread even if the chatter was
        unavailable when it started.

        The new body is pushed on the message bus as well as stored, so the
        author watching the record sees the placeholder swap for the answer as
        it lands rather than on their next reload. Odoo's own edit helper is
        deliberately not used: it stamps the note as edited, and nobody edited
        it. Like Odoo's own edit path this reaches the acting user's tabs, so
        other readers still pick the answer up on reload.
        """
        if not self.is_mention:
            return
        message = self.answer_message_id.sudo()
        if not message:
            self._post_mention_placeholder()
            return
        message.write({'body': self._mention_answer_body()})
        with suppress(Exception):
            Store(bus_channel=message._bus_channel()).add(message, ['body']).bus_send()

    # ----------------------------------------------------------
    # Helper Compose
    # ----------------------------------------------------------

    @api.model
    def _compose_agent(self) -> models.BaseModel:
        """Return the agent a writing helper runs under.

        The space collecting the helpers may name one, which is how an admin
        points them at an agent tuned for writing. Otherwise the company
        default answers, as everywhere else.
        """
        space = self.env.ref('muk_ai_chatter.space_writing', raise_if_not_found=False)
        if space and space.sudo().agent_id.active:
            return space.sudo().agent_id
        return self.env['muk_ai.agent']._get_default()

    @api.model
    def _open_composer_session(self, interface_key: str) -> models.BaseModel:
        """Return the writing helper this user already has, if any.

        One helper per composer, reused every time the panel is opened: a new
        session per rewrite would leave somebody who wrote ten messages with
        ten chats they never had. It is pointed at whatever is being written
        each time it opens, so it carries nothing of the last one but the
        conversation the user had with it.

        :param interface_key: the composer asking, see ``COMPOSE_INTERFACES``
        """
        return self.search(
            [
                ('user_id', '=', self.env.uid),
                ('compose_interface', '=', interface_key),
                ('state', 'not in', ('running', 'compacting', 'waiting')),
            ],
            order='id desc',
            limit=1,
        )

    @api.model
    def _compose_context_values(
        self, res_model: str | None, res_id: int | None
    ) -> dict:
        """Return what the composer is writing about, as prompt context.

        The helper is not linked to the record, but must still know which one
        it writes about, so the record stands as the view context and its
        conversation is snapshotted. Read as the user, so a helper never
        tells them about a record they could not have opened themselves.
        """
        blank = {'mention_context': '', 'view_context': False}
        if not res_model or not res_id or res_model not in self.env:
            return blank
        record = self.env[res_model].browse(res_id)
        if not record.exists() or not record.has_access('read'):
            return blank
        return {
            'mention_context': (
                record._ai_thread_context()
                if hasattr(record, '_ai_thread_context')
                else ''
            ),
            'view_context': {
                'kind': 'record',
                'model': record._name,
                'id': record.id,
                'display_name': record.display_name,
            },
        }

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    def open_for_composer(
        self,
        interface_key: str,
        res_model: str | None = None,
        res_id: int | None = None,
        draft: str | None = None,
        selection: str | None = None,
    ) -> dict:
        """Open a session that helps write the message a composer holds.

        The draft and the selected part are stored on the session rather than
        pushed as a first prompt, so every turn the user asks for is answered
        against the same text, and the chat window can take the session over
        with all of it still in place.

        Both arrive as the plain text the user sees, and are kept as they are:
        a composer holds prose, and anything shaped like a tag in it —
        ``a <5``, ``<todo>`` — is something they typed, not markup to strip.

        The record is read for its conversation and for what it is, then let
        go: the helper is not linked to it. What it writes is a draft nobody
        has sent, and the record has no business carrying a note about it,
        listing it among its chats, or keeping it once the message is gone.
        Both are read again on every opening, so a reply answers the message
        that is there now rather than the one that was there yesterday.

        :param interface_key: which composer asked, see ``COMPOSE_INTERFACES``
        :param res_model: model of the record the composer writes about
        :param res_id: identifier of that record
        :param draft: what the user has typed so far, as plain text
        :param selection: the part of the draft to rewrite, if any
        :return: the session snapshot the overlay drives its state from
        :raise UserError: when no agent is configured to answer
        """
        agent = self._compose_agent()
        if not agent:
            raise UserError(_('No AI agent is available to help you write.'))
        interface = (
            interface_key
            if interface_key in dict(COMPOSE_INTERFACES)
            else 'mail_composer'
        )
        values = {
            'compose_interface': interface,
            **compose_text_values(draft, selection),
            **self._compose_context_values(res_model, res_id),
        }
        existing = self._open_composer_session(interface)
        if existing:
            if existing._compose_target_changed(values):
                existing._reset_for_new_target()
            existing.write(values)
            return existing.get_snapshot()
        session = self.create(
            {'name': _('Writing helper'), 'agent_id': agent.id, **values}
        )
        return session.get_snapshot()

    def update_compose_context(
        self, draft: str | None = None, selection: str | None = None
    ) -> bool:
        """Point an open writing helper at what the composer holds now.

        The user keeps typing while the overlay is open, and a second request
        has to work on what is on screen rather than on what was there when
        the helper started.
        """
        self.ensure_one()
        self.write(compose_text_values(draft, selection))
        return True

    def discard_unused_composer(self) -> bool:
        """Drop a writing helper that was opened and never asked anything.

        The session is opened when the panel is, so the first chip does not
        wait for one. A user who looks at the offers and dismisses the panel
        would otherwise leave a chat behind for a message they never wrote.

        :return: whether the session was dropped
        """
        self.ensure_one()
        if not self.compose_interface or self.state != 'new' or self.conversation:
            return False
        self.unlink()
        return True

    def send_message(
        self, user_message: str, attachment_ids: list[int] | None = None
    ) -> dict:
        """Remind a writing helper what an answer looks like, every turn.

        A tool-using agent tends to close with a report of what it did — "I
        drafted a reply, review it in the composer" — which is exactly what
        must not land in somebody's message. Saying so once in the system
        prompt loses against the habit; saying it again in the turn itself
        does not.
        """
        if self.compose_interface and user_message:
            user_message = COMPOSE_TURN_REMINDER % user_message
        return super().send_message(user_message, attachment_ids=attachment_ids)

    def detach_from_composer(self) -> bool:
        """Hand a writing helper over to the chat window as an ordinary chat.

        The overlay offers a draft and two buttons, which is why the helper
        runs with no approvals, no questions and no client tools. In a chat
        window the user is there to answer, so those restrictions are lifted;
        the draft and the conversation stay on the session as context.
        """
        self.ensure_one()
        self.compose_interface = False
        return True

    # ----------------------------------------------------------
    # ORM methods
    # ----------------------------------------------------------

    def _notify_state_transition(self, payload: dict) -> None:
        """Fold the finished run back into the note the mention was answered with.

        Compaction publishes a ``done`` of its own from inside a running turn,
        so the same context key the base uses to stay quiet is honoured here —
        otherwise the thread would show an answer while the agent is still
        working, and keep it until the run really ends.
        """
        super()._notify_state_transition(payload)
        state = (payload or {}).get('state')
        if state == 'done' and (
            self.pending_ids or self.env.context.get('muk_ai_skip_done_notification')
        ):
            return
        if state in ('done', 'stopped', 'error'):
            self._refresh_mention_answer()

    @api.model_create_multi
    def create(self, vals_list: list[dict]) -> AISession:
        """Create sessions, mirroring a note onto linked business records.

        A mention already answers itself in the thread, so it is spared the
        mirror note that would otherwise announce the very session the user is
        reading the answer of. So is a writing helper: it is opened by clicking
        into a composer, and announcing that in the record's log would put a
        note there for every message somebody thought about writing.
        """
        records = super().create(vals_list)
        for record in records:
            if not record.res_model or not record.res_id:
                continue
            if record.mention_message_id or record.compose_interface:
                continue
            record._post_chatter_mirror()
        return records
