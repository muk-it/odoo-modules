from __future__ import annotations

from odoo import api, models

CHATTER_SESSION_LIMIT = 10


class MailThread(models.AbstractModel):
    """Expose linked AI sessions to the chatter of any threaded record."""

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
            'previous_session_id',
            'action_server_id',
            'error_message',
        ]

    def _get_ai_sessions_for_chatter(self) -> models.BaseModel:
        """Return the linked sessions the current user is allowed to read."""
        sessions = (
            self.env['muk_ai.session']
            .sudo()
            .search(
                [('res_model', '=', self._name), ('res_id', '=', self.id)],
                order='create_date desc',
                limit=CHATTER_SESSION_LIMIT,
            )
        )
        return sessions.with_user(self.env.user).filtered(
            lambda session: session.has_access('read')
        )

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    def get_ai_sessions_summary(self) -> dict:
        """Return per-record linked-session entries and total counts."""
        Session = self.env['muk_ai.session']
        names = self._ai_session_chatter_fields()
        result = {}
        for thread in self:
            sessions = thread._get_ai_sessions_for_chatter()
            result[thread.id] = {
                'entries': sessions.sudo().read(names),
                'total': Session.search_count(
                    [('res_model', '=', thread._name), ('res_id', '=', thread.id)],
                ),
            }
        return result
