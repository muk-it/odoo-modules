from __future__ import annotations

from odoo import fields, models


class IrActionsServer(models.Model):
    """Add the ``ai_session`` server-action state running pending sessions."""

    _inherit = 'ir.actions.server'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    state = fields.Selection(
        selection_add=[('ai_session', 'AI Session Worker')],
        ondelete={'ai_session': 'cascade'},
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _run_action_ai_session(self, eval_context=None) -> None:
        """Run pending AI sessions for a single-record server action."""
        self.env['muk_ai.session']._cron_run_pending_sessions()

    def _run_action_ai_session_multi(self, eval_context=None) -> None:
        """Run pending AI sessions for a multi-record server action."""
        self.env['muk_ai.session']._cron_run_pending_sessions()
