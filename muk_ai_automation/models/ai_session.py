from __future__ import annotations

from odoo import fields, models

from odoo.addons.muk_ai_automation.tools.prompt import PreviousProxy


class AISession(models.Model):
    """Link AI chats to the server action that started them."""

    _inherit = 'muk_ai.session'

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

    action_server_usage = fields.Selection(
        related='action_server_id.usage',
        string='Started By Usage',
        store=True,
    )

    action_space_id = fields.Many2one(
        related='action_server_id.agent_space_id',
        string='Space of the Action',
        store=True,
        index=True,
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

    def _should_autoname(self) -> bool:
        """Keep the name of a chat a server action started."""
        return not self.action_server_id and super()._should_autoname()

    def _should_notify_state(self, state: str) -> bool:
        """Stay quiet about a chat a server action finished, report the rest."""
        if self.action_server_id and state == 'done':
            return False
        return super()._should_notify_state(state)

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
