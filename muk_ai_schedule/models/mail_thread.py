from odoo import api, models

CHATTER_SESSION_LIMIT = 10


class MailThread(models.AbstractModel):

    _inherit = 'mail.thread'

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _ai_session_chatter_fields(self):
        return [
            'id', 'name', 'state', 'create_date', 'user_id', 'agent_id',
            'schedule_id', 'previous_session_id', 'resume_at',
            'iteration_count', 'error_message',
        ]

    def _get_ai_sessions_for_chatter(self):
        sessions = self.env['muk_ai.session'].sudo().search(
            [('res_model', '=', self._name), ('res_id', '=', self.id)],
            order='create_date desc',
            limit=CHATTER_SESSION_LIMIT,
        )
        return sessions.with_user(self.env.user).filtered(
            lambda session: session.has_access('read')
        )

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    def get_ai_sessions_summary(self):
        Session = self.env['muk_ai.session'].sudo()
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
