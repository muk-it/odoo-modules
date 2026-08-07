from __future__ import annotations

from odoo import _, api, models

from odoo.addons.muk_ai_chatter.tools import (
    CHATTER_SESSION_LIMIT,
    THREAD_CONTEXT_MESSAGES,
    THREAD_CONTEXT_TYPES,
    format_thread_context,
    mention_plaintext,
)


class MailThread(models.AbstractModel):
    """Expose the AI sessions held against a record to its chatter."""

    _inherit = 'mail.thread'

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _ai_session_chatter_fields(self) -> list[str]:
        """Return the session fields read for the chatter summary."""
        return [
            'id',
            'name',
            'state',
            'create_date',
            'user_id',
            'agent_id',
        ]

    def _ai_session_chatter_domain(self) -> list:
        """Return the domain for the linked sessions the caller may see.

        A session belongs to whoever ran it: the transcript carries tool
        output gathered under that user's rights, so reading the record it is
        pinned to never opens the conversation held against it.
        """
        domain = [('res_model', '=', self._name), ('res_id', '=', self.id)]
        if not self.env.is_admin():
            domain.append(('user_id', '=', self.env.uid))
        return domain

    def _get_ai_sessions_for_chatter(self) -> models.BaseModel:
        """Return the linked sessions shown in this record's chatter."""
        return (
            self.env['muk_ai.session']
            .sudo()
            .search(
                self._ai_session_chatter_domain(),
                order='create_date desc',
                limit=CHATTER_SESSION_LIMIT,
            )
        )

    # ----------------------------------------------------------
    # Helper Mention
    # ----------------------------------------------------------

    def _ai_split_mentioned_agents(
        self, partner_ids: list[int] | None
    ) -> tuple[models.BaseModel, list[int]]:
        """Split mentioned agents off the recipients of a message.

        The agents are dropped from ``partner_ids`` so no post notifies them,
        mails them, or enrols them as followers — on every thread, whether or
        not it is one they answer in. A poster who may not run a session gets
        no agent back, only the stripping.

        :param partner_ids: the mentioned partners the client sent
        :return: the mentionable agents, and the partner ids left to notify
        """
        empty = self.env['muk_ai.agent']
        if not partner_ids:
            return empty, list(partner_ids or [])
        partners = self.env['res.partner'].sudo().browse(list(partner_ids))
        standing_in = partners._ai_agent_partners()
        if not standing_in:
            return empty, list(partner_ids or [])
        remaining = [pid for pid in partner_ids if pid not in set(standing_in.ids)]
        if not self.env['muk_ai.session'].has_access('create'):
            return empty, remaining
        return standing_in._mentionable_ai_agents(), remaining

    def _ai_answer_mentions(
        self, message: models.BaseModel, agents: models.BaseModel
    ) -> None:
        """Answer the agents mentioned in this thread, if it is one they serve.

        Nothing happens on a record: a chatter message is addressed to the
        people following the record, and an agent answering it there reads as
        mail somebody sent. The writing helper is the surface for a record.
        """

    def _ai_thread_context(self) -> str:
        """Return the recorded conversation of this record as prompt data.

        Snapshotted once when a mention spawns its session: chatter messages
        are editable and deletable, so re-reading them later would silently
        change what the agent was told.
        """
        messages = (
            self.env['mail.message']
            .sudo()
            .search(
                [
                    ('model', '=', self._name),
                    ('res_id', '=', self.id),
                    ('message_type', 'in', THREAD_CONTEXT_TYPES),
                ],
                order='id desc',
                limit=THREAD_CONTEXT_MESSAGES,
            )
        )
        lines = []
        for message in reversed(messages):
            body = mention_plaintext(message.body)
            if not body:
                continue
            author = message.author_id.display_name or message.email_from or _('System')
            stamp = message.date.strftime('%Y-%m-%d %H:%M') if message.date else ''
            lines.append(f'[{stamp}] {author}: {body}')
        return format_thread_context(lines)

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    def get_ai_sessions_summary(self) -> dict:
        """Return per-record linked-session entries and total counts."""
        Session = self.env['muk_ai.session'].sudo()
        names = self._ai_session_chatter_fields()
        result = {}
        for thread in self:
            sessions = thread._get_ai_sessions_for_chatter()
            result[thread.id] = {
                'entries': sessions.read(names),
                'total': Session.search_count(thread._ai_session_chatter_domain()),
            }
        return result

    # ----------------------------------------------------------
    # ORM methods
    # ----------------------------------------------------------

    def message_post(
        self, *, partner_ids: list[int] | None = None, **kwargs
    ) -> models.BaseModel:
        """Post the message, keeping any mentioned agent out of its recipients."""
        agents, recipients = self._ai_split_mentioned_agents(partner_ids)
        message = super().message_post(partner_ids=recipients, **kwargs)
        self._ai_answer_mentions(message, agents)
        return message

    def _message_update_content(
        self,
        message: models.BaseModel,
        /,
        *,
        partner_ids: list[int] | None = None,
        **kwargs,
    ) -> None:
        """Keep an agent out of the recipients of an edited message too.

        Editing summons nobody: a mention is answered once, when it is written.
        ``None`` is how the caller says it is not editing them at all.
        """
        if partner_ids is not None:
            partner_ids = self._ai_split_mentioned_agents(partner_ids)[1]
        super()._message_update_content(message, partner_ids=partner_ids, **kwargs)
