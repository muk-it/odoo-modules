from odoo import fields, models


class IrActionsServer(models.Model):

    _inherit = 'ir.actions.server'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    state = fields.Selection(
        selection_add=[('ai_session', "AI Session Worker")],
        ondelete={'ai_session': 'cascade'},
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _run_action_ai_session(self, eval_context=None):
        self.env['muk_ai.session']._cron_run_pending_sessions()

    def _run_action_ai_session_multi(self, eval_context=None):
        self.env['muk_ai.session']._cron_run_pending_sessions()
