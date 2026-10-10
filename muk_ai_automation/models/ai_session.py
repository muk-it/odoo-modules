from __future__ import annotations

from odoo import fields, models

from odoo.addons.muk_ai_automation.tools.prompt import PreviousProxy


class AISession(models.Model):
    """Link AI chats to the server action that started them."""

    _inherit = 'muk_ai.session'

    _explanation = (
        'A chat can also be started by a server action, an automation rule or '
        'a scheduled action running an AI agent, and continue the chat the same '
        'action ran for the same record before.'
    )

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    action_server_id = fields.Many2one(
        comodel_name='ir.actions.server',
        string='Started By',
        help='Server action that started this chat.',
        index=True,
        copy=False,
        ondelete='set null',
    )

    previous_session_id = fields.Many2one(
        comodel_name='muk_ai.session',
        string='Previous Chat',
        help='Chat the same action ran for the same record before this one.',
        copy=False,
        ondelete='set null',
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _available_client_kinds(self) -> set[str]:
        """Offer no browser-executed tool to a chat a server action started."""
        kinds = super()._available_client_kinds()
        if self.action_server_id:
            kinds.discard('webclient')
        return kinds

    def _session_prompt_extras(self) -> dict:
        """Expose the linked record, the previous chat and the time to the prompt."""
        record = self._linked_record()
        return {
            **super()._session_prompt_extras(),
            'now': fields.Datetime.now(),
            'record': (
                record.with_user(self.user_id or self.env.user)
                if record is not None
                else self.env['base']
            ),
            'previous_session': PreviousProxy(self.previous_session_id),
        }
