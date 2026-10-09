from __future__ import annotations

from contextlib import suppress

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.mail import plaintext2html

from odoo.addons.muk_ai.models.session import has_access
from odoo.addons.muk_ai.tools.context import with_record_ctx
from odoo.addons.muk_ai_chatter.tools.chatter import (
    fenced,
    linkify_records,
    session_link,
)
from odoo.addons.muk_ai_chatter.tools.compose import (
    COMPOSE_INTERFACES,
    COMPOSE_TURN_REMINDER,
    compose_addenda,
    compose_text_values,
)
from odoo.addons.muk_ai_chatter.tools.mention import MENTION_RULES


class AISession(models.Model):
    """Link AI sessions to a record, answer mentions and help write messages."""

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
            'decides the guard rails, and stays set when the mention is deleted.'
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
            'Conversation recorded on the record when the session started, kept '
            'as it was then, whatever is edited in the thread afterwards.'
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

    @property
    def _is_unattended(self) -> bool:
        """Return whether nobody can answer this run: a mention or a writing helper."""
        return self.is_mention or bool(self.compose_interface)

    def _linked_record(self) -> models.BaseModel | None:
        """Return the linked record when it exists and the owner may read it."""
        if not self.res_model or not self.res_id or self.res_model not in self.env:
            return None
        record = self.env[self.res_model].sudo().browse(self.res_id)
        if not record.exists():
            return None
        owner = self.user_id or self.env.user
        return record if has_access(record.with_user(owner), 'read') else None

    def _bus_send_audience(self, notification_type: str, message: dict) -> None:
        """Tell the chat lists, the chatter's among them, which record a session runs for."""
        if notification_type == 'muk_ai.session_state':
            message = {
                **message,
                'res_model': self.res_model or False,
                'res_id': self.res_id or False,
            }
        super()._bus_send_audience(notification_type, message)

    def _skill_scope_context(self) -> dict | None:
        """Stand the linked record in for a view the session never had."""
        context = super()._skill_scope_context()
        if context:
            return context
        record = self._linked_record()
        if record is None:
            return None
        return {'kind': 'record', 'model': record._name, 'id': record.id}

    def _enforce_tool_scope(self) -> str | None:
        """Hold a writing helper to read-only tools."""
        if self.compose_interface:
            return 'read'
        return super()._enforce_tool_scope()

    def _effective_approval_mode(self) -> str:
        """Never pause an unattended run to ask for approval."""
        if self._is_unattended:
            return 'off'
        return super()._effective_approval_mode()

    def _can_ask_user(self) -> bool:
        """Refuse an unattended run the right to stop and ask."""
        if self._is_unattended:
            return False
        return super()._can_ask_user()

    def _available_client_kinds(self) -> set[str]:
        """Offer no client-executed tool to a run no chat window hosts."""
        if self._is_unattended:
            return set()
        return super()._available_client_kinds()

    def _should_autoname(self) -> bool:
        """Keep the name a mention or a writing helper was opened under."""
        if self._is_unattended:
            return False
        return super()._should_autoname()

    def _should_notify_state(self) -> bool:
        """Stay quiet about a writing helper, whose panel shows the run."""
        if self.compose_interface:
            return False
        return super()._should_notify_state()

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
        """Extend request inputs with the linked record and the composer reminder."""
        inputs = super()._build_request_inputs()
        if self.compose_interface:
            inputs = [*inputs, COMPOSE_TURN_REMINDER]
        record = self._linked_record()
        if record is None:
            return inputs
        return with_record_ctx(
            inputs,
            {
                'kind': 'record',
                'model': record._name,
                'id': record.id,
                'display_name': record.display_name,
            },
        )

    def _session_link(self, label: str | None = None) -> Markup:
        """Return a chatter link opening this session."""
        return session_link(self.id, label or self.display_name)

    def _post_chatter_mirror(self) -> None:
        """Post a note on the linked record pointing at this session."""
        record = self._linked_record()
        if record is None or not hasattr(record, 'message_post'):
            return
        body = Markup('<p>%s</p>') % _(
            'AI session %(link)s started for this record.',
            link=self._session_link(),
        )
        with suppress(Exception), self.env.cr.savepoint():
            record.message_post(body=body, subtype_xmlid='mail.mt_note')

    def _mention_answer_body(self) -> Markup:
        """Return the note body reporting where this mention has got to.

        A failure is not detailed: the thread reaches people the run does not.
        """
        footer = Markup('<p class="text-muted small">%s</p>') % self._session_link(
            _('View the run')
        )
        if self.state == 'error':
            text = _('The agent could not answer. The run says why.')
        elif self.state in ('done', 'stopped') and self.last_text:
            body = plaintext2html(self.last_text)
            return linkify_records(body, lambda model: model in self.env) + footer
        elif self.state in ('done', 'stopped'):
            text = _('The agent had nothing to add.')
        else:
            return Markup('<p><i>%s</i></p>') % _('Working on it...')
        return Markup('<p><i>%s</i></p>') % text + footer

    def _post_mention_placeholder(self) -> None:
        """Answer the mention at once with a note the run fills in later."""
        record = self._linked_record()
        if record is None:
            return
        with suppress(Exception), self.env.cr.savepoint():
            self.answer_message_id = record.with_context(
                mail_post_autofollow=False,
                mail_post_autofollow_author_skip=True,
            ).message_post(
                body=self._mention_answer_body(),
                author_id=self.agent_id.partner_id.id,
                message_type='comment',
                subtype_xmlid='mail.mt_comment',
                parent_id=self.mention_message_id.id or False,
            )

    def _refresh_mention_answer(self) -> None:
        """Rewrite the answer note in place, or post it when it went missing.

        The body is pushed on the bus as well, without the edited stamp
        Odoo's own edit helper would put on a note nobody edited.
        """
        if not self.is_mention:
            return
        message = self.answer_message_id.sudo()
        if not message:
            self._post_mention_placeholder()
            return
        message.write({'body': self._mention_answer_body()})
        self.env['bus.bus']._sendone(
            message._bus_notification_target(),
            'mail.record/insert',
            {'Message': {'id': message.id, 'body': message.body}},
        )

    @api.model
    def _compose_agent(self) -> models.BaseModel:
        """Return the agent of the composer space, else the default agent."""
        space = self.env.ref('muk_ai_chatter.space_writing', raise_if_not_found=False)
        if space and space.sudo().agent_id.active:
            return space.sudo().agent_id
        return self.env['muk_ai.agent']._get_default()

    @api.model
    def _compose_context_values(
        self, res_model: str | None, res_id: int | None
    ) -> dict:
        """Return the record a composer writes about and its thread, read as the user."""
        blank = {'mention_context': '', 'view_context': False}
        if not res_model or not res_id or res_model not in self.env:
            return blank
        record = self.env[res_model].browse(res_id)
        if not record.exists() or not has_access(record, 'read'):
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

    def _compose_target_changed(self, values: dict) -> bool:
        """Return whether the helper is pointed at text it has not seen.

        Asking again about the same draft and selection keeps the
        conversation; new text, or an empty composer, starts clean.
        """
        draft = values.get('compose_draft') or ''
        if not draft:
            return True
        return (self.compose_draft or '', self.compose_selection or '') != (
            draft,
            values.get('compose_selection') or '',
        )

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
        """Open the user's writing helper of a composer and return its snapshot.

        One helper per composer and user is reused; the record is context only.

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
        session = self.search(
            [
                ('user_id', '=', self.env.uid),
                ('compose_interface', '=', interface),
                ('state', 'not in', ('running', 'compacting', 'waiting')),
            ],
            order='id desc',
            limit=1,
        )
        if not session:
            session = self.create(
                {
                    'name': _('Writing helper'),
                    'agent_id': agent.id,
                    **values,
                }
            )
            return session.get_snapshot()
        if session._compose_target_changed(values):
            session.clear()
            session.invalidate_recordset(['event_ids'])
            session.event_ids.unlink()
        session.write(values)
        return session.get_snapshot()

    def update_compose_context(
        self, draft: str | None = None, selection: str | None = None
    ) -> bool:
        """Point an open writing helper at what the composer holds now."""
        self.ensure_one()
        self.write(compose_text_values(draft, selection))
        return True

    def discard_unused_composer(self) -> bool:
        """Drop a writing helper that was opened and never asked anything.

        :return: whether the session was dropped
        """
        self.ensure_one()
        if not self.compose_interface or self.state != 'new' or self.conversation:
            return False
        self.unlink()
        return True

    def detach_from_composer(self) -> bool:
        """Hand a writing helper over to the chat window as an ordinary chat."""
        self.ensure_one()
        self.compose_interface = False
        return True

    # ----------------------------------------------------------
    # ORM
    # ----------------------------------------------------------

    def _notify_state_transition(self, payload: dict) -> None:
        """Fold the run that came to rest back into the mention's answer note."""
        super()._notify_state_transition(payload)
        state = payload.get('state')
        if state == 'done' and (
            self.pending_ids or self.env.context.get('muk_ai_skip_done_notification')
        ):
            return
        if state in ('done', 'stopped', 'error'):
            self._refresh_mention_answer()

    @api.model_create_multi
    def create(self, vals_list: list[dict]) -> AISession:
        """Create sessions, announcing a plain linked one on its record."""
        records = super().create(vals_list)
        for record in records:
            if record.res_id and not record._is_unattended:
                record._post_chatter_mirror()
        return records
