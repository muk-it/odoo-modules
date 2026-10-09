from __future__ import annotations

import logging

from odoo import _, models

from odoo.addons.muk_ai.models.session import has_access
from odoo.addons.muk_ai_chatter.tools.chatter import CHATTER_SESSION_LIMIT
from odoo.addons.muk_ai_chatter.tools.mention import (
    THREAD_CONTEXT_MESSAGES,
    THREAD_CONTEXT_TYPES,
    format_thread_context,
    mention_plaintext,
)

_logger = logging.getLogger(__name__)


class MailThread(models.AbstractModel):
    """Expose the AI sessions of a record to its chatter and strip agent recipients."""

    _inherit = 'mail.thread'

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _ai_session_chatter_domain(self) -> list:
        """Return the linked sessions the caller may see: their own, all for a settings admin."""
        domain = [('res_model', '=', self._name), ('res_id', '=', self.id)]
        if not self.env.user._is_system():
            domain.append(('user_id', '=', self.env.uid))
        return domain

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _ai_split_mentioned_agents(
        self, partner_ids: list[int] | None
    ) -> tuple[models.BaseModel, list[int]]:
        """Return the agents that answer and the partner ids left to notify.

        Agents never become recipients or followers; a poster who may not run
        a session gets no agent back, only the stripping.
        """
        agents = self.env['muk_ai.agent']
        partners = self.env['res.partner'].sudo().browse(partner_ids or [])
        standing_in = partners._ai_agent_partners()
        if not standing_in:
            return agents, list(partner_ids or [])
        remaining = [pid for pid in partner_ids if pid not in standing_in.ids]
        if has_access(self.env['muk_ai.session'], 'create'):
            agents = standing_in._mentionable_ai_agents()
        return agents, remaining

    def _ai_answer_mentions(
        self, message: models.BaseModel, agents: models.BaseModel
    ) -> None:
        """Answer the agents mentioned in this thread; a record answers none."""

    def _ai_thread_context(self) -> str:
        """Return the recorded conversation of this record as prompt data."""
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
            if body := mention_plaintext(message.body):
                author = (
                    message.author_id.display_name or message.email_from or _('System')
                )
                stamp = message.date.strftime('%Y-%m-%d %H:%M')
                lines.append(f'[{stamp}] {author}: {body}')
        return format_thread_context(lines)

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    def get_ai_sessions_summary(self) -> dict:
        """Return per record the newest linked sessions and their total count."""
        sessions = self.env['muk_ai.session'].sudo()
        result = {}
        for thread in self:
            domain = thread._ai_session_chatter_domain()
            result[thread.id] = {
                'entries': sessions.search_read(
                    domain,
                    ['name', 'state', 'create_date', 'user_id', 'agent_id'],
                    order='create_date desc',
                    limit=CHATTER_SESSION_LIMIT,
                ),
                'total': sessions.search_count(domain),
            }
        return result

    # ----------------------------------------------------------
    # ORM
    # ----------------------------------------------------------

    def message_post(
        self, *, partner_ids: list[int] | None = None, **kwargs
    ) -> models.BaseModel:
        """Post the message with the agents out of its recipients, then answer them.

        Answering runs in a savepoint: a run that refuses to start loses the
        answer, never the message.
        """
        agents, recipients = self._ai_split_mentioned_agents(partner_ids)
        message = super().message_post(partner_ids=recipients, **kwargs)
        if agents:
            try:
                with self.env.cr.savepoint():
                    self._ai_answer_mentions(message, agents)
            except Exception:
                _logger.exception(
                    'Could not answer the agents mentioned in message %s', message.id
                )
        return message

    def _message_update_content(
        self,
        message: models.BaseModel,
        body: str | None,
        attachment_ids: list[int] | None = None,
        partner_ids: list[int] | None = None,
        **kwargs,
    ) -> None:
        """Keep the agents out of the recipients of an edited message, summoning none."""
        if partner_ids is not None:
            partner_ids = self._ai_split_mentioned_agents(partner_ids)[1]
        super()._message_update_content(
            message,
            body,
            attachment_ids=attachment_ids,
            partner_ids=partner_ids,
            **kwargs,
        )
